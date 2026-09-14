#!/usr/bin/env bash
# Pemasang write_noop_guard.py — DIJALANKAN PETER, bukan agen (doktrin: agen dilarang
# memasang berkas penegaknya sendiri). Idempoten. Batal bila suite regresi gagal.
set -euo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$PKG/.." && pwd)"
DST="${SAMEWRITE_DST:-$HOME/scripts/write_noop_guard.py}"
# Profil: `CLAUDE_CONFIG_DIR` adalah cara resmi CLI menunjuk direktori config lain, dan mesin
# dengan dua akun punya dua settings.json. Memasang ke ~/.claude tanpa melihat env berarti
# memasang ke profil yang mungkin tidak sedang dipakai — hook lalu "tak jalan" tanpa sebab.
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SET="${SAMEWRITE_SETTINGS:-$CFG/settings.json}"
[ -f "$SET" ] || { echo "BATAL: $SET tak ada. Set CLAUDE_CONFIG_DIR ke profil yang benar, atau SAMEWRITE_SETTINGS ke berkasnya."; exit 1; }
PY_BIN="${SAMEWRITE_PYTHON:-$(command -v python3)}"
[ -x "$PY_BIN" ] || { echo "BATAL: python3 tak ditemukan (set SAMEWRITE_PYTHON)"; exit 1; }
echo "profil: $CFG"

echo "[1/4] suite regresi…"
"$PY_BIN" "$ROOT/tests/test_write_noop_guard.py" >/tmp/wng_test.out 2>&1 || {
  echo "BATAL: suite GAGAL:"; tail -6 /tmp/wng_test.out; exit 1; }
tail -1 /tmp/wng_test.out

echo "[2/4] pasang guard -> $DST"
install -m 0755 "$PKG/write_noop_guard.py" "$DST"

echo "[3/4] daftarkan hook PreToolUse(Write) di settings.json"
cp -a "$SET" "$SET.bak.wng.$(date -u +%Y%m%d_%H%M%S)"
LEDGER="${SAMEWRITE_LEDGER:-$HOME/logs/samewrite.jsonl}"
mkdir -p "$(dirname "$LEDGER")"
# Kutip POSIX ('...' dengan ' -> '\'') — bukan printf %q, yang untuk newline memakai $'...' khas bash
# sedangkan perintah hook dijalankan shell yang tidak kita pilih. Path berspasi/metakarakter aman.
q() { printf "'%s'" "$(printf %s "$1" | sed "s/'/'\\\\''/g")"; }
HOOKCMD="SAMEWRITE_LEDGER=$(q "$LEDGER") $(q "$PY_BIN") $(q "$DST")"
echo "   ledger: $LEDGER"
"$PY_BIN" - "$SET" "$HOOKCMD" "$DST" <<'PY'
import json,shlex,sys
p, CMD, DST = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(p))
pre=d.setdefault("hooks",{}).setdefault("PreToolUse",[])
def owns(cmd):   # milik kita = token yang PERSIS path guard terpasang, bukan substring nama berkas
    try:
        return DST in shlex.split(cmd)
    except ValueError:
        return False
if any(owns(h.get("command","")) for m in pre for h in m.get("hooks",[])):
    print("   sudah terpasang — tak ada perubahan"); sys.exit(0)
pre.append({"matcher":"Write","hooks":[{"type":"command","command":CMD}]})
json.dump(d,open(p,"w"),indent=2,ensure_ascii=False); open(p,"a").write("\n")
print("   entri ditambahkan")
PY

# Opsional (SAMEWRITE_OUTPUT_HOOK=1): satu kalimat output samewrite disuntik saat SessionStart
# (startup|resume|clear|compact) lewat printf — nol skrip, ~170 byte per sesi. Kalimatnya =
# kalimat PERTAMA bagian "## Output" di skills/samewrite/SKILL.md (uji drift: tests/test_adapters.py).
# Pilot presentasi 14-Sep: 7/8 kasus human_ok vs 5/8 tanpa hook (n=8, arah bukan signifikansi).
if [ "${SAMEWRITE_OUTPUT_HOOK:-0}" = "1" ]; then
  echo "[3b/4] daftarkan hook SessionStart satu-kalimat output"
  OUTCMD="printf '%s\\n' 'Lead with the result, blocker, or next action. Use numbered steps only for user actions; omit unchanged state, recaps, and generic closers. Expand when requested.' # samewrite-output-hook"
  "$PY_BIN" - "$SET" "$OUTCMD" <<'PYX'
import json,sys
p, CMD = sys.argv[1], sys.argv[2]
d = json.load(open(p))
ss = d.setdefault("hooks", {}).setdefault("SessionStart", [])
if any(h.get("command") == CMD for m in ss for h in m.get("hooks", [])):
    print("   sudah terpasang — tak ada perubahan"); sys.exit(0)
ss.append({"matcher": "startup|resume|clear|compact", "hooks": [{"type": "command", "command": CMD}]})
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False); open(p, "a").write("\n")
print("   entri SessionStart ditambahkan")
PYX
  sh -c "$OUTCMD" | grep -q "Lead with the result" && echo "   hook output menjawab: OK" || { echo "   GAGAL: hook output bisu"; exit 1; }
fi

echo "[4/4] verifikasi konsumen — guard dijalankan lewat jalur nyata"
export SAMEWRITE_ROOT="$(dirname "$DST")"
printf '%s' '{"tool_name":"Write","tool_input":{"file_path":"'"$DST"'","content":"x"}}' \
  | "$PY_BIN" "$DST" | grep -q deny && echo "   ANEH: isi beda kok ditolak" || echo "   allow utk isi beda: OK"
printf '{"tool_name":"Write","tool_input":{"file_path":%s,"content":%s}}' \
  "$("$PY_BIN" -c 'import json;print(json.dumps("'"$DST"'"))')" \
  "$("$PY_BIN" -c 'import json;print(json.dumps(open("'"$DST"'").read()))')" \
  | "$PY_BIN" "$DST" | grep -q deny && echo "   deny utk isi identik: OK" || { echo "   GAGAL: identik tak ditolak"; exit 1; }
echo
echo "SELESAI. Berlaku di sesi Claude Code BERIKUTNYA (settings.json dibaca saat start)."
echo "Cabut: hapus entri 'write_noop_guard.py' dari $SET, atau pulihkan $SET.bak.wng.*"
