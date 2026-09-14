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
import json, os, re, stat, sys, time

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


def note(event, _target=None, **fields):
    """Catat satu baris JSONL bila SAMEWRITE_LEDGER diset. Sengaja bebas-identitas:
    tanpa path, tanpa isi, tanpa nama berkas. Gagal menulis tak pernah menghalangi kerja.

    `_target` = berkas yang sedang dinilai. Kalau ledger menunjuk berkas yang SAMA, menulis
    ke sana akan MENGUBAH berkas yang baru saja dinyatakan tak berubah — pemeriksaan no-op
    yang justru menghasilkan dua baris baru lalu menolak write-nya."""
    p = os.environ.get(LEDGER_ENV)
    if not p:
        return
    if _target:
        try:
            if os.path.realpath(p) == os.path.realpath(_target):
                return
        except Exception:
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


# `cat > f <<'EOF'` lewat Bash menulis berkas persis seperti Write, tetapi tidak pernah
# melewati matcher Write — dan pengukuran arsip menemukan 1.136 tulis-ulang berkas lewat
# jalur itu yang isinya SAMA PERSIS. Menutup satu pintu sementara pintu sebelahnya
# terbuka bukan penegakan, itu dekorasi.
#
# ⚠️ TIDAK DIPASANG OLEH `hooks/install.sh`. Installer mendaftarkan matcher `Write` SAJA,
# dan itu disengaja: lihat angka di bawah. Kode jalur Bash ada dan teruji, tapi menyalakannya
# butuh menambahkan `Bash` ke matcher secara sadar — bukan efek samping memasang guard ini.
# ⚠️ JANGKAUAN TERUKUR DI KORPUS PENULIS: **0 dari 1.136**. Kode di bawah benar dan
# tesnya lulus, tapi ia tak pernah cocok dengan lalu lintas nyata, karena **100% no-op
# heredoc di arsip punya perintah SESUDAH bloknya** (88,7% perintah lain, 11,3% chmod) —
# nol yang berdiri sendiri. Syarat "perintah tunggal" ada demi KEBENARAN: menolak
# `cat > f <<'EOF' … EOF` yang diikuti `chmod +x f` ikut membatalkan chmod-nya, dan itu
# bukan no-op. Kebenaran dan jangkauan di sini saling meniadakan.
# Angka ini DIBIARKAN di sini alih-alih kodenya dihapus diam-diam: yang berikut membaca
# berhak tahu jalur ini sudah dicoba, dan kenapa ia tak membayar. Jangan pasang matcher
# Bash atas dasar kode ini tanpa mengukur ulang jangkauannya di korpusmu sendiri.
#
# Sengaja SEMPIT — tiap syarat di bawah ada karena melanggarnya membuat jawaban SALAH,
# bukan karena kehati-hatian umum:
#   - tag WAJIB terkutip (<<'EOF'). Tanpa kutip, shell mengekspansi $VAR dan `cmd` di
#     dalam body, jadi teks mentah yang kita banding BUKAN yang akan mendarat di disk.
#   - hanya `>`, bukan `>>`: append dengan isi sama BUKAN no-op.
#   - perintah harus tunggal. `cat > f <<'EOF' ... EOF` lalu `chmod +x f` adalah satu
#     panggilan Bash: menolaknya ikut membatalkan chmod, yang bukan no-op.
# HANYA `cat > f`. `tee f` sempat didukung lalu DICABUT (review ronde-2): `tee` juga
# menulis body ke STDOUT, jadi menolaknya membuang keluaran yang mungkin dipakai pipa
# berikutnya — perintah itu bukan no-op meski isi berkasnya identik.
HEREDOC = re.compile(
    r"""^\s*(?:
            cat\s*>\s*(?!>)                    # cat > f   (timpa saja, bukan >>)
        )
        (?P<path>"[^"]+"|'[^']+'|[^\s<>|&;-][^\s<>|&;]*)
        \s*<<\s*(?P<q>['"])(?P<tag>[A-Za-z_][\w]*)(?P=q)\s*\n
        (?P<body>.*?)\n
        (?P=tag)\s*$                           # tag penutup = akhir perintah
    """, re.S | re.X)


def heredoc_write(cmd):
    """(path, body) untuk penulisan heredoc yang aman dibandingkan; None selain itu."""
    if not isinstance(cmd, str) or "<<" not in cmd:
        return None
    m = HEREDOC.match(cmd.strip())
    if not m:
        return None
    raw = m.group("path")
    # Buang SATU lapis kutip pembungkus, dan hanya kalau ia benar-benar berpasangan.
    # `.strip("\"'")` yang lama memakan kutip yang merupakan bagian SAH dari nama berkas:
    # `cat > 'f"'` menulis berkas bernama `f"`, bukan `f`.
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        path = raw[1:-1]
    else:
        path = raw
        if '"' in path or "'" in path:
            return None                       # kutip di tengah: jangan menebak
    # Path yang akan DIEKSPANSI shell bukan path yang ditulis: `cat > "$(printf f)"`
    # menulis berkas `f`, tapi kita akan membandingkan berkas bernama `$(printf f)`.
    # Menebak hasil ekspansi = menebak; menolak = melewatkan satu kasus. Melewatkan
    # aman, salah-tuduh memblokir kerja yang benar.
    if any(ch in path for ch in "$`*?[]{}~\\") or not path:
        return None
    return path, m.group("body") + "\n"


def samewrite_disabled():
    """`samewrite off` / `stop samewrite` (hooks/samewrite_mode.py) leaves one marker,
    `<state dir>/samewrite-disabled`; every samewrite hook stands down while it exists.
    Same resolution order as the mode hook — the two must agree or "off" is a lie."""
    try:
        d = (os.environ.get("SAMEWRITE_STATE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
             or os.path.join(os.path.expanduser("~"), ".claude"))
        return os.path.lexists(os.path.join(d, "samewrite-disabled"))
    except Exception:
        return False


def main():
    if os.environ.get(ESCAPE) == "1" or samewrite_disabled():
        allow()
    try:
        raw = sys.stdin.read(MAX_STDIN + 1)
        if len(raw) > MAX_STDIN:
            allow()
        data = json.loads(raw or "{}")
    except Exception:
        allow()
    if not isinstance(data, dict):
        allow()
    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict):
        allow()
    if tool == "Write":
        path = ti.get("file_path")
        new = ti.get("content")
    elif tool == "Bash":
        hit = heredoc_write(ti.get("command"))
        if not hit:
            allow()
        path, new = hit
    else:
        allow()
    if not path or not isinstance(path, str) or not isinstance(new, str):
        allow()
    if sensitive(path):
        allow()                          # jangan jadi oracle atas berkas rahasia
    try:                                 # confinement: di luar workspace, bukan urusan kita
        root = os.path.realpath(os.environ.get(ROOT_ENV) or os.getcwd())
        real = os.path.realpath(path)    # realpath menyelesaikan symlink SEBELUM keputusan
        if os.path.commonpath([root, real]) != root:
            allow()
        # Nama symlink bisa TAK bernilai-rahasia sementara targetnya rahasia: sebuah tautan
        # bernama polos yang menunjuk berkas kredensial lolos `sensitive(path)` di atas, lalu
        # isinya dibaca dan jawaban deny/allow menjadi oracle kesetaraan atas berkas yang hook
        # lain sengaja larang dibaca. Periksa target yang SUDAH diresolusi juga.
        if sensitive(real):
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
        note("checked", _target=path, bytes=len(new_b), same=True)
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
