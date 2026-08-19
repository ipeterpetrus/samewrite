#!/usr/bin/env python3
"""PreToolUse(Write) — tolak Write yang isinya IDENTIK dengan berkas di disk.

Dasar ukur: 24 transcript / 29.838 turn / 122 Write-menimpa -> 18 (15%) isinya
persis sama dengan versi sebelumnya. 11.923 token output terbuang, 10.083.748
token carry (0,076%). Nol trade-off: operasinya memang tak perlu dilakukan.

FAIL-OPEN by design: guard ini menghemat token, bukan mencegah kerusakan.
Bug di sini tidak boleh memblok kerja -> error apa pun = allow.
Perbandingan BYTE-EXACT pada byte MENTAH (mode biner): beda whitespace, newline, atau
CRLF/LF = perubahan nyata dan lewat. Path bernilai-rahasia dilewati agar jawaban
deny/allow tak menjadi oracle kesetaraan atas isinya.
"""
import json, os, stat, sys

MAX_BYTES = 8 * 1024 * 1024   # ponytail: berkas raksasa dilewati, bukan dibaca ke memori
MAX_STDIN = 64 * 1024 * 1024  # payload lebih besar dari ini: jangan dimuat, langsung allow
# Path bernilai-rahasia dilewati. Bukan karena guard membocorkan isi — ia tidak — tapi
# karena jawaban deny/allow adalah ORACLE KESETARAAN: pemanggil bisa menebak isi berkas
# lalu membaca hasilnya. Untuk berkas yang hook lain sengaja larang dibaca, itu bypass.
DOTENV = "." + "env"
SENS_SUFFIX = (".pem", ".p12", ".pfx", ".key", ".keystore", ".jks")
SENS_WORDS = ("secret", "credential", "token", "passw", "shadow",
              "keychain", "id_rsa", "id_ed25519", "id_ecdsa", "private_key")
SENS_DIRS = ("/.ssh/", "/.gnupg/", "/.aws/", "/.kube/", "/.docker/", "/.config/gh/")


def sensitive(path):
    """Path bernilai-rahasia dilewati: jawaban deny/allow adalah oracle kesetaraan,
    dan untuk berkas yang hook lain sengaja larang dibaca, itu jalur bypass."""
    p = path.lower().replace(chr(92), "/")
    base = p.rsplit("/", 1)[-1]
    if base == DOTENV or base.startswith(DOTENV + "."):
        return True
    return (p.endswith(SENS_SUFFIX) or any(w in p for w in SENS_WORDS)
            or any(dd in p for dd in SENS_DIRS))


ESCAPE = "CARRYTAX_ALLOW_NOOP"
ROOT_ENV = "CARRYTAX_ROOT"      # batasi guard ke satu pohon direktori; kosong = cwd  # =1 -> guard mati; utk penulisan identik yang DISENGAJA
                                # (memicu file-watcher, menyegarkan mtime, uji idempotensi)


def allow():
    sys.exit(0)


def deny(reason):
    try:                              # broken pipe / stdout aneh tak boleh jadi status error
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    except Exception:
        pass
    sys.exit(0)


def main():
    if os.environ.get(ESCAPE) == "1":
        allow()
    try:
        raw = sys.stdin.read(MAX_STDIN + 1)
        if len(raw) > MAX_STDIN:
            allow()
        data = json.loads(raw or "{}")
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
    if sensitive(path):
        allow()                          # jangan jadi oracle atas berkas rahasia
    try:                                 # confinement: di luar workspace, bukan urusan kita
        root = os.path.realpath(os.environ.get(ROOT_ENV) or os.getcwd())
        real = os.path.realpath(path)    # realpath menyelesaikan symlink SEBELUM keputusan
        if os.path.commonpath([root, real]) != root:
            allow()
    except Exception:
        allow()
    try:
        st_ = os.stat(path)
        if not stat.S_ISREG(st_.st_mode):
            allow()                      # berkas baru, FIFO, device, direktori: bukan urusan kita
        if st_.st_size > MAX_BYTES:
            allow()
        # BINER, bukan mode teks: mode "r" menerjemahkan CRLF -> LF sehingga Write sah yang
        # menormalkan akhir baris akan tampak "identik" dan diblokir. Bukan teori — ditemukan
        # auditor lintas-famili pada versi sebelumnya.
        with open(path, "rb") as fh:
            cur = fh.read(MAX_BYTES + 1)  # /proc & sejenisnya lapor size 0 tapi mengalir terus
        if len(cur) > MAX_BYTES:
            allow()
        new_b = new.encode("utf-8")
    except Exception:
        allow()                          # tak terbaca / biner / izin -> jangan halangi
    if cur == new_b:
        n = new.count("\n") + (0 if new.endswith("\n") or not new else 1)
        deny(
            f"Write DITOLAK: isi identik dengan {path} yang sudah di disk "
            f"({len(new_b)} byte, {n} baris) — nol perubahan, token output terbuang. "
            f"Berkas sudah dalam keadaan yang kamu inginkan; lanjut ke langkah berikutnya. "
            f"Kalau memang perlu mengubah, kirim isi yang berbeda atau pakai Edit. "
            f"Penulisan identik yang disengaja: jalankan dengan {ESCAPE}=1."
        )
    allow()


if __name__ == "__main__":
    main()
