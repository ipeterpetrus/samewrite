#!/usr/bin/env bash
# Pemasang write_noop_guard.py — DIJALANKAN PETER, bukan agen (doktrin: agen dilarang
# memasang berkas penegaknya sendiri). Idempoten. Batal bila suite regresi gagal.
set -euo pipefail
PKG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$PKG/.." && pwd)"
DST=/home/ubuntu/scripts/write_noop_guard.py
SET=/home/ubuntu/.claude/settings.json

echo "[1/4] suite regresi…"
/usr/bin/python3 "$ROOT/tests/test_write_noop_guard.py" >/tmp/wng_test.out 2>&1 || {
  echo "BATAL: suite GAGAL:"; tail -6 /tmp/wng_test.out; exit 1; }
tail -1 /tmp/wng_test.out

echo "[2/4] pasang guard -> $DST"
install -m 0755 "$PKG/write_noop_guard.py" "$DST"

echo "[3/4] daftarkan hook PreToolUse(Write) di settings.json"
cp -a "$SET" "$SET.bak.wng.$(date -u +%Y%m%d_%H%M%S)"
/usr/bin/python3 - "$SET" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p))
CMD="bash /home/ubuntu/scripts/hook_logwrap.sh PreToolUse:write_noop_guard.py 'python3 /home/ubuntu/scripts/write_noop_guard.py'"
pre=d.setdefault("hooks",{}).setdefault("PreToolUse",[])
if any(CMD in h.get("command","") for m in pre for h in m.get("hooks",[])):
    print("   sudah terpasang — tak ada perubahan"); sys.exit(0)
pre.append({"matcher":"Write","hooks":[{"type":"command","command":CMD}]})
json.dump(d,open(p,"w"),indent=2,ensure_ascii=False); open(p,"a").write("\n")
print("   entri ditambahkan")
PY

echo "[4/4] verifikasi konsumen — guard dijalankan lewat jalur nyata"
printf '%s' '{"tool_name":"Write","tool_input":{"file_path":"'"$DST"'","content":"x"}}' \
  | /usr/bin/python3 "$DST" | grep -q deny && echo "   ANEH: isi beda kok ditolak" || echo "   allow utk isi beda: OK"
printf '{"tool_name":"Write","tool_input":{"file_path":%s,"content":%s}}' \
  "$(/usr/bin/python3 -c 'import json;print(json.dumps("'"$DST"'"))')" \
  "$(/usr/bin/python3 -c 'import json;print(json.dumps(open("'"$DST"'").read()))')" \
  | /usr/bin/python3 "$DST" | grep -q deny && echo "   deny utk isi identik: OK" || { echo "   GAGAL: identik tak ditolak"; exit 1; }
echo
echo "SELESAI. Berlaku di sesi Claude Code BERIKUTNYA (settings.json dibaca saat start)."
echo "Cabut: hapus entri 'write_noop_guard.py' dari $SET, atau pulihkan $SET.bak.wng.*"
