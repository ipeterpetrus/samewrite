#!/usr/bin/env python3
"""PreToolUse(Write) — tolak Write yang isinya IDENTIK dengan berkas di disk.

Dasar ukur: 1.316 transcript / 237.541 turn / 741 Write-menimpa -> 154 (20,8%)
isinya persis sama dengan versi sebelumnya; 0,077% carry. Nyaris nol trade-off:
operasinya memang tak perlu dilakukan (biayanya satu stat + satu baca).

FAIL-OPEN by design: guard ini menghemat token, bukan mencegah kerusakan.
Bug di sini tidak boleh memblok kerja -> error apa pun = allow.
Perbandingan BYTE-EXACT pada byte MENTAH (mode biner): beda whitespace, newline, atau
CRLF/LF = perubahan nyata dan lewat. Path bernilai-rahasia dilewati agar jawaban
deny/allow tak menjadi oracle kesetaraan atas isinya.
"""
import json, os, stat, sys, time

MAX_BYTES = 8 * 1024 * 1024   # ponytail: berkas raksasa dilewati, bukan dibaca ke memori
MAX_STDIN = 64 * 1024 * 1024  # payload lebih besar dari ini: jangan dimuat, langsung allow
MAX_DIFF_LINES = 5000         # ponytail: di atas ini blok tak dihitung (difflib O(n*m));
                              # telemetri hilang, keputusan deny/allow TIDAK berubah
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


ESCAPE = "SAMEWRITE_ALLOW_NOOP"
LEDGER_ENV = "SAMEWRITE_LEDGER"  # opsional: path JSONL. Yang dicatat hanya UKURAN dan
                                 # hasil — tak pernah path, isi, atau nama berkas.
ROOT_ENV = "SAMEWRITE_ROOT"      # batasi guard ke satu pohon direktori; kosong = cwd  # =1 -> guard mati; utk penulisan identik yang DISENGAJA
                                # (memicu file-watcher, menyegarkan mtime, uji idempotensi)


def allow():
    sys.exit(0)


def diffstat(cur_b, new_b):
    """-> (blok baris berubah, fraksi byte berubah) atau None.

    Telemetri murni: tak pernah menyentuh keputusan deny/allow. `frac` adalah fitur
    yang dipakai skill edit-discipline sejak korpus 1.316-transcript menunjukkan
    jumlah blok memilih kasus yang salah; `blocks` tetap dicatat supaya aturan lama
    bisa terus diuji terhadap aturan baru pada data yang sama.
    None = tak dihitung (terlalu besar, atau gagal)."""
    try:
        a = cur_b.decode("utf-8", "replace").splitlines()
        b = new_b.decode("utf-8", "replace").splitlines()
        if max(len(a), len(b)) > MAX_DIFF_LINES:
            return None
        import difflib   # impor lokal: jalur deny tak perlu membayarnya
        blocks = changed = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b,
                                                           autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            blocks += 1
            changed += sum(len(x) + 1 for x in a[i1:i2]) + sum(len(x) + 1 for x in b[j1:j2])
        return blocks, changed / max(1, len(new_b))
    except Exception:
        return None


def note(event, **fields):
    """Catat satu baris JSONL bila SAMEWRITE_LEDGER diset. Sengaja bebas-identitas:
    tanpa path, tanpa isi, tanpa nama berkas. Gagal menulis tak pernah menghalangi kerja."""
    p = os.environ.get(LEDGER_ENV)
    if not p:
        return
    try:
        rec = {"ts": int(time.time()), "host": os.uname().nodename, "event": event}
        rec.update(fields)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


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
        note("checked", bytes=len(new_b), same=True)
        n = new.count("\n") + (0 if new.endswith("\n") or not new else 1)
        note("denied", bytes=len(new_b), lines=n)
        deny(
            f"Write DITOLAK: isi identik dengan {path} yang sudah di disk "
            f"({len(new_b)} byte, {n} baris) — nol perubahan, token output terbuang. "
            f"Berkas sudah dalam keadaan yang kamu inginkan; lanjut ke langkah berikutnya. "
            f"Kalau memang perlu mengubah, kirim isi yang berbeda atau pakai Edit. "
            f"Penulisan identik yang disengaja: jalankan dengan {ESCAPE}=1."
        )
    d = diffstat(cur, new_b)             # sampai di sini = isi BEDA
    note("checked", bytes=len(new_b), same=False, cur_bytes=len(cur),
         **({"blocks": d[0], "frac": round(d[1], 4)} if d is not None else {}))
    allow()


if __name__ == "__main__":
    main()
