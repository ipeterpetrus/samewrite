#!/usr/bin/env bash
# Pencabut hook samewrite — DIJALANKAN PETER/pengguna, bukan agen. Idempoten.
# Hanya menyentuh entri hook yang perintahnya memuat berkas MILIK samewrite
# (write_noop_guard.py / samewrite_mode.py). Hook lain, statusLine, dan kunci lain
# di settings.json dibiarkan byte-per-byte. JSON rusak -> peringatan, tak disentuh.
set -euo pipefail
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SET="${SAMEWRITE_SETTINGS:-$CFG/settings.json}"
PY_BIN="${SAMEWRITE_PYTHON:-$(command -v python3)}"
DST="${SAMEWRITE_DST:-$HOME/scripts/write_noop_guard.py}"     # sama dengan install.sh
STATE="${SAMEWRITE_STATE_DIR:-$CFG}"                            # sama dengan samewrite_mode.py
[ -f "$SET" ] || { echo "tak ada $SET — tak ada yang dicabut"; exit 0; }
cp -a "$SET" "$SET.bak.samewrite-uninstall.$(date -u +%Y%m%d_%H%M%S)"
"$PY_BIN" - "$SET" "$DST" "$(dirname "$DST")/samewrite_mode.py" <<'PY'
import json, os, shlex, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception as e:
    print("PERINGATAN: %s bukan JSON yang bisa dibaca (%s) — TIDAK disentuh." % (p, e))
    sys.exit(1)
OWN = set(sys.argv[2:4])   # path PERSIS yang install.sh pasang — hook asing yang kebetulan
                            # bernama sama di direktori lain bukan milik kita (review 14-Sep)
def own(cmd):
    try:
        return any(tok in OWN for tok in shlex.split(str(cmd)))
    except ValueError:
        return False
removed = 0
hooks = d.get("hooks")
if isinstance(hooks, dict):
    for ev in list(hooks):
        kept = []
        for m in hooks[ev]:
            hs = [h for h in m.get("hooks", []) if not own(h.get("command", ""))]
            removed += len(m.get("hooks", [])) - len(hs)
            if hs:
                m["hooks"] = hs
                kept.append(m)
        if kept:
            hooks[ev] = kept
        else:
            del hooks[ev]
    if not hooks:
        del d["hooks"]
if removed:
    json.dump(d, open(p, "w"), indent=2, ensure_ascii=False); open(p, "a").write("\n")
print("entri samewrite dicabut: %d (statusLine dan hook lain tak disentuh)" % removed)
PY
rm -f "$STATE/samewrite-disabled"
echo "Berkas guard/mode di ~/scripts (atau SAMEWRITE_DST) sengaja dibiarkan; hapus manual bila mau."
