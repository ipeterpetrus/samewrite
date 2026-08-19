#!/usr/bin/env python3
"""Suite mandiri utk write_noop_guard.py — pola ~/scripts: nol runner agregat,
   skrip ini sendiri menghitung PASS/FAIL dan mengembalikan exit bukan-nol."""
import json, os, subprocess, sys, tempfile

G = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "write_noop_guard.py")
PASS = FAIL = 0
ROOT = [os.getcwd()]                          # diisi tempdir saat tes berjalan


def run(payload, env=None):
    e = dict(os.environ); e.pop("CARRYTAX_ALLOW_NOOP", None)
    e["CARRYTAX_ROOT"] = ROOT[0]              # guard dibatasi ke pohon kerja; tes menyetelnya
    if env: e.update(env)
    p = subprocess.run(["/usr/bin/python3", G], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=20, env=e)
    denied = '"deny"' in p.stdout
    return denied, p.stdout, p.returncode


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1; print(f"  PASS  {name}")
    else:
        FAIL += 1; print(f"  FAIL  {name}: dapat deny={got}, harap deny={want}")


def w(d, name, body):
    p = os.path.join(d, name)
    with open(p, "w") as fh: fh.write(body)
    return p


with tempfile.TemporaryDirectory() as d:
    ROOT[0] = d
    same = w(d, "same.txt", "line1\nline2\n")
    empty = w(d, "empty.txt", "")
    missing = os.path.join(d, "tidak_ada.txt")

    # 1-2: inti
    check("isi identik -> DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2\n"}})[0], True)
    check("beda 1 karakter -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline3\n"}})[0], False)
    # 3: trailing newline = perubahan nyata
    check("beda trailing newline -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2"}})[0], False)
    # 4: whitespace = perubahan nyata (byte-exact, sengaja)
    check("beda spasi trailing -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1 \nline2\n"}})[0], False)
    # 5: berkas baru
    check("berkas belum ada -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": missing, "content": "apa pun"}})[0], False)
    # 6: kosong == kosong
    check("kosong vs kosong -> DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": empty, "content": ""}})[0], True)
    # 7: tool lain tak tersentuh
    check("tool_name=Edit -> allow",
          run({"tool_name": "Edit", "tool_input": {"file_path": same, "content": "line1\nline2\n"}})[0], False)
    check("tool_name=Bash -> allow",
          run({"tool_name": "Bash", "tool_input": {"command": "ls"}})[0], False)
    # 8: fail-open
    check("stdin bukan JSON -> allow",
          subprocess.run(["/usr/bin/python3", G], input="{bukan json",
                         capture_output=True, text=True).stdout.find('"deny"') >= 0, False)
    check("tool_input hilang -> allow",
          run({"tool_name": "Write"})[0], False)
    check("content bukan string -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": 123}})[0], False)
    check("file_path kosong -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": "", "content": "x"}})[0], False)
    # 9: direktori, bukan berkas
    check("path = direktori -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": d, "content": "x"}})[0], False)
    # 10: biner tak ter-decode utf-8
    b = os.path.join(d, "bin.dat")
    with open(b, "wb") as fh: fh.write(b"\xff\xfe\x00\x01")
    check("berkas biner -> allow (fail-open)",
          run({"tool_name": "Write", "tool_input": {"file_path": b, "content": "x"}})[0], False)
    # 11: exit code selalu 0 (jangan bikin harness marah)
    check("exit code 0 saat DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2\n"}})[2], 0)
    # 12: alasan deny menyebut path
    d2, out, _ = run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2\n"}})
    check("alasan deny memuat path", same in out, True)
    # 13: kasus NYATA dari transcript — 164 baris identik
    big = "\n".join(f"baris ke-{i} dengan isi panjang supaya mirip skrip nyata" for i in range(164)) + "\n"
    p164 = w(d, "hold_cap.sh", big)
    check("164 baris identik (kasus nyata) -> DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": p164, "content": big}})[0], True)
    check("164 baris, 1 baris diubah -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": p164,
               "content": big.replace("baris ke-100", "baris ke-100 DIUBAH")}})[0], False)

    # 14: escape hatch — penulisan identik yang DISENGAJA harus lolos
    check("CARRYTAX_ALLOW_NOOP=1 -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2\n"}},
              env={"CARRYTAX_ALLOW_NOOP": "1"})[0], False)
    check("CARRYTAX_ALLOW_NOOP=0 -> tetap DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2\n"}},
              env={"CARRYTAX_ALLOW_NOOP": "0"})[0], True)
    # 15: FIFO tidak boleh membuat guard menggantung
    fifo = os.path.join(d, "pipa")
    os.mkfifo(fifo)
    check("FIFO -> allow tanpa menggantung",
          run({"tool_name": "Write", "tool_input": {"file_path": fifo, "content": "x"}})[0], False)
    # 16: symlink ke berkas identik tetap terdeteksi
    ln = os.path.join(d, "tautan.txt"); os.symlink(same, ln)
    check("symlink ke isi identik -> DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": ln, "content": "line1\nline2\n"}})[0], True)
    # 17: alasan deny menyebut escape hatch
    _, out17, _ = run({"tool_name": "Write", "tool_input": {"file_path": same, "content": "line1\nline2\n"}})
    check("alasan deny menyebut CARRYTAX_ALLOW_NOOP", "CARRYTAX_ALLOW_NOOP" in out17, True)

    # 18: CRLF — normalisasi akhir baris adalah perubahan NYATA
    crlf = os.path.join(d, "crlf.txt")
    with open(crlf, "wb") as fh: fh.write(b"line1\r\nline2\r\n")
    check("disk CRLF vs tulis LF -> allow",
          run({"tool_name": "Write", "tool_input": {"file_path": crlf, "content": "line1\nline2\n"}})[0], False)
    check("disk CRLF vs tulis CRLF -> DENY",
          run({"tool_name": "Write", "tool_input": {"file_path": crlf, "content": "line1\r\nline2\r\n"}})[0], True)
    # 19: pesan harus menghitung BYTE, bukan karakter
    uni = w(d, "uni.txt", "h\u00e9llo w\u00f6rld\n")
    _, out19, _ = run({"tool_name": "Write", "tool_input": {"file_path": uni, "content": "h\u00e9llo w\u00f6rld\n"}})
    check("pesan pakai byte (14) bukan karakter (12)", "14 byte" in out19, True)
    # 20: oracle-guard — path rahasia dilewati walau identik
    for nm in ("." + "env", "id_rsa", "my_" + "secret.txt", "app.key"):
        pp = w(d, nm, "NILAI\n")
        check("path sensitif %s -> allow" % nm,
              run({"tool_name": "Write", "tool_input": {"file_path": pp, "content": "NILAI\n"}})[0], False)

    # 21: confinement — berkas identik DI LUAR workspace tidak diurus
    import tempfile as _tf
    with _tf.TemporaryDirectory() as outside:
        po = os.path.join(outside, "luar.txt")
        with open(po, "w") as fh: fh.write("sama\n")
        check("di luar CARRYTAX_ROOT -> allow",
              run({"tool_name": "Write", "tool_input": {"file_path": po, "content": "sama\n"}})[0], False)

print(f"\n{PASS} PASS / {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
