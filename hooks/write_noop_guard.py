#!/usr/bin/env python3
"""PreToolUse(Write) — tolak Write yang isinya IDENTIK dengan berkas di disk.

Dasar ukur: 24 transcript / 29.838 turn / 122 Write-menimpa -> 18 (15%) isinya
persis sama dengan versi sebelumnya. 11.923 token output terbuang, 10.083.748
token carry (0,076%). Nol trade-off: operasinya memang tak perlu dilakukan.

FAIL-OPEN by design: guard ini menghemat token, bukan mencegah kerusakan.
Bug di sini tidak boleh memblok kerja -> error apa pun = allow.
Perbandingan BYTE-EXACT: beda whitespace/newline = perubahan nyata, dibiarkan lewat.
"""
import json, os, sys

MAX_BYTES = 8 * 1024 * 1024   # ponytail: berkas raksasa dilewati, bukan dibaca ke memori


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
        if not os.path.isfile(path):
            allow()                      # berkas baru = Write sah
        if os.path.getsize(path) > MAX_BYTES:
            allow()
        with open(path, "r", encoding="utf-8", errors="strict") as fh:
            cur = fh.read()
    except Exception:
        allow()                          # tak terbaca / biner / izin -> jangan halangi
    if cur == new:
        n = new.count("\n") + (0 if new.endswith("\n") or not new else 1)
        deny(
            f"Write DITOLAK: isi identik dengan {path} yang sudah di disk "
            f"({len(new)} byte, {n} baris) — nol perubahan, token output terbuang. "
            f"Berkas sudah dalam keadaan yang kamu inginkan; lanjut ke langkah berikutnya. "
            f"Kalau memang perlu mengubah, kirim isi yang berbeda atau pakai Edit."
        )
    allow()


if __name__ == "__main__":
    main()
