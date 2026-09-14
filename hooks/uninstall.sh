#!/usr/bin/env bash
# Pencabut hook samewrite — DIJALANKAN PETER/pengguna, bukan agen. Idempoten.
# Hanya menyentuh entri hook yang perintahnya memuat berkas MILIK samewrite
# (write_noop_guard.py / samewrite_mode.py). Hook lain, statusLine, dan kunci lain
# di settings.json dibiarkan byte-per-byte. JSON rusak -> peringatan, tak disentuh.
set -euo pipefail
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SET="${SAMEWRITE_SETTINGS:-$CFG/settings.json}"
PY_BIN="${SAMEWRITE_PYTHON:-$(command -v python3)}"
[ -f "$SET" ] || { echo "tak ada $SET — tak ada yang dicabut"; exit 0; }
cp -a "$SET" "$SET.bak.samewrite-uninstall.$(date -u +%Y%m%d_%H%M%S)"
"$PY_BIN" - "$SET" <<'PY'
import json, os, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception as e:
    print("PERINGATAN: %s bukan JSON yang bisa dibaca (%s) — TIDAK disentuh." % (p, e))
    sys.exit(1)
OWN = ("write_noop_guard.py", "samewrite_mode.py")
def own(cmd):
    base = [t.rsplit("/", 1)[-1] for t in str(cmd).split()]
    return any(b in OWN for b in base)
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
rm -f "$CFG/samewrite-disabled"
echo "Berkas guard/mode di ~/scripts (atau SAMEWRITE_DST) sengaja dibiarkan; hapus manual bila mau."
