#!/usr/bin/env python3
"""Ronde 5. Tiga perbedaan dari runner sebelumnya:

1. ORACLE KETIGA (holdout): pemanggil BARU ditulis SESUDAH tambalan agen mendarat. ROOT
   menuntut target + tetangga + holdout hijau. Tetangga bisa ditebak; pemanggil yang belum
   ada saat agen bekerja tidak bisa.
2. LENGAN PLACEBO: prompt sepanjang lengan skill yang mendorong deliberasi TANPA menyebut
   akar/kelas. Panel adv-max menyebut 'anggaran, bukan penalaran' sebagai penjelasan
   non-kausal terkuat: lengan skill memakai +51-80% token, jadi mungkin yang menolong cuma
   berpikir lebih lama. Placebo memisahkan keduanya; tanpa lengan ini efek apa pun tak bisa
   diatribusikan ke isi skill-nya.
3. Skor holdout ikut menentukan vonis, jadi tambalan di situs pemanggil tak bisa lulus.
"""
import argparse, hashlib, json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures5 as fx

CLAUDE = os.path.expanduser("~/.local/bin/claude")
BASE = ("Uji di test_target.py gagal. Perbaiki kode sumbernya sehingga uji itu lulus. "
        "JANGAN menyunting berkas uji apa pun. Balas 'SELESAI' saat sudah.")
ARM = {
    "plain": BASE,
    "placebo": ("Kerjakan dengan tenang dan teliti: baca dulu berkas yang relevan, tuliskan "
                "rencana singkat sebelum menyunting, lalu periksa kembali hasilmu. " + BASE),
    "skill": "Panggil skill systematic-debugging lebih dulu dan ikuti prosesnya. " + BASE,
}


def pytest(d, f):
    return subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", f],
                          cwd=d, capture_output=True, timeout=180).returncode


def one(name, arm, model, timeout, cfg):
    work = tempfile.mkdtemp(prefix=f"sd5-{name}-{arm}-")
    d, neighbor = fx.build(work, name)
    tests = {f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
             for f in os.listdir(d) if f.startswith("test_")}
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
    t0 = time.time()
    try:
        p = subprocess.run([CLAUDE, "-p", ARM[arm], "--model", model,
                            "--permission-mode", "acceptEdits"],
                           cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
        rc = p.returncode
        open(os.path.join(d, "_agent_stdout.txt"), "w").write(p.stdout or "")
    except subprocess.TimeoutExpired:
        rc = -1
    dt = time.time() - t0
    if any(hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest() != h
           for f, h in tests.items()):
        verdict, parts = "INVALID", None
    else:
        open(os.path.join(d, "test_neighbor.py"), "w").write(neighbor)
        fx.add_holdout(d, name)
        t = pytest(d, "test_target.py")
        n = pytest(d, "test_neighbor.py")
        h = pytest(d, "test_holdout.py")
        parts = dict(target=t, neighbor=n, holdout=h)
        verdict = "FAIL" if t else ("ROOT" if (n == 0 and h == 0) else "SYMPTOM")
    return dict(fixture=name, arm=arm, verdict=verdict, parts=parts, rc=rc,
                sec=round(dt, 1), work=work)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--only", default="")
    ap.add_argument("--arms", default="plain,placebo,skill")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--out", default="results5.jsonl")
    a = ap.parse_args()
    names = [x for x in (a.only.split(",") if a.only else sorted(fx.F)) if x]
    for r in range(a.repeat):
        for name in names:
            for arm in [x for x in a.arms.split(",") if x]:
                res = one(name, arm, a.model, a.timeout, a.config_dir)
                res.update(rep=r, model=a.model)
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res) + "\n")
                print(f"{name:16s} {arm:8s} rep{r} -> {res['verdict']:8s} "
                      f"({res['sec']}s, rc={res['rc']})", flush=True)


if __name__ == "__main__":
    main()
