#!/usr/bin/env python3
"""PreToolUse(Write) — tolak Write yang isinya IDENTIK dengan berkas di disk.

Dasar ukur: 24 transcript / 29.838 turn / 122 Write-menimpa -> 18 (15%) isinya
persis sama dengan versi sebelumnya. 11.923 token output terbuang, 10.083.748
token carry (0,076%). Nol trade-off: operasinya memang tak perlu dilakukan.

FAIL-OPEN by design: guard ini menghemat token, bukan mencegah kerusakan.
Bug di sini tidak boleh memblok kerja -> error apa pun = allow.
Perbandingan BYTE-EXACT: beda whitespace/newline = perubahan nyata, dibiarkan lewat.
"""
import json, os, stat, sys

MAX_BYTES = 8 * 1024 * 1024   # ponytail: berkas raksasa dilewati, bukan dibaca ke memori
ESCAPE = "CARRYTAX_ALLOW_NOOP"  # =1 -> guard mati; utk penulisan identik yang DISENGAJA
                                # (memicu file-watcher, menyegarkan mtime, uji idempotensi)


def allow():
    sys.exit(0)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    if os.environ.get(ESCAPE) == "1":
        allow()
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        allow()
    if not isinstance(data, dict) or data.get("tool_name") != "Write":
        allow()
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        allow()
    path = ti.get("file_path")
    new = ti.get("content")
    if not path or not isinstance(path, str) or not isinstance(new, str):
        allow()
    try:
        st_ = os.stat(path)
        if not stat.S_ISREG(st_.st_mode):
            allow()                      # berkas baru, FIFO, device, direktori: bukan urusan kita
        if st_.st_size > MAX_BYTES:
            allow()
        with open(path, "r", encoding="utf-8", errors="strict") as fh:
            cur = fh.read(MAX_BYTES + 1)  # /proc & sejenisnya lapor size 0 tapi mengalir terus
        if len(cur) > MAX_BYTES:
            allow()
    except Exception:
        allow()                          # tak terbaca / biner / izin -> jangan halangi
    if cur == new:
        n = new.count("\n") + (0 if new.endswith("\n") or not new else 1)
        deny(
            f"Write DITOLAK: isi identik dengan {path} yang sudah di disk "
            f"({len(new)} byte, {n} baris) — nol perubahan, token output terbuang. "
            f"Berkas sudah dalam keadaan yang kamu inginkan; lanjut ke langkah berikutnya. "
            f"Kalau memang perlu mengubah, kirim isi yang berbeda atau pakai Edit. "
            f"Penulisan identik yang disengaja: jalankan dengan {ESCAPE}=1."
        )
    allow()


if __name__ == "__main__":
    main()
