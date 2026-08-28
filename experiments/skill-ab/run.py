#!/usr/bin/env python3
"""Ronde 2. Sama seperti run.py tapi (a) fixture multi-berkas, (b) CLAUDE_CONFIG_DIR
minimal — tanpa CLAUDE.md, hook, atau plugin milik host.

Alasan (b) bukan sekadar hemat: di ronde 1 tiap run menyeret preamble ~45 kB milik host
plus belasan hook, jadi yang terukur adalah "Claude Code + seluruh konfigurasi Peter",
bukan "Claude Code + skill yang diuji". Konfigurasi minimal mengisolasi variabelnya.
"""
import argparse, hashlib, json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures2 as fx

CLAUDE = os.path.expanduser("~/.local/bin/claude")
BASE = ("Uji di test_target.py gagal. Perbaiki kode sumbernya sehingga uji itu lulus. "
        "JANGAN menyunting berkas uji apa pun. Balas 'SELESAI' saat sudah.")
ARM = {
    "plain": BASE,
    "skill": "Panggil skill systematic-debugging lebih dulu dan ikuti prosesnya. " + BASE,
}


def pytest(d, f):
    return subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", f],
                          cwd=d, capture_output=True, timeout=180).returncode


def one(name, arm, model, timeout, cfg):
    work = tempfile.mkdtemp(prefix=f"sd2-{name}-{arm}-")
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
    tampered = any(hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest() != h
                   for f, h in tests.items())
    if tampered:
        verdict = "INVALID"
    else:
        open(os.path.join(d, "test_neighbor.py"), "w").write(neighbor)
        t = pytest(d, "test_target.py")
        n = pytest(d, "test_neighbor.py")
        verdict = "FAIL" if t else ("ROOT" if n == 0 else "SYMPTOM")
    return dict(fixture=name, arm=arm, verdict=verdict, rc=rc, sec=round(dt, 1), work=work)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--only", default="")
    ap.add_argument("--arms", default="plain,skill")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--config-dir", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "minicfg"))
    ap.add_argument("--out", default="results2.jsonl")
    a = ap.parse_args()
    names = [x for x in (a.only.split(",") if a.only else sorted(fx.F)) if x]
    arms = [x for x in a.arms.split(",") if x]
    for r in range(a.repeat):
        for name in names:
            for arm in arms:
                res = one(name, arm, a.model, a.timeout, a.config_dir)
                res.update(rep=r, model=a.model)
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res) + "\n")
                print(f"{name:14s} {arm:6s} rep{r} -> {res['verdict']:8s} "
                      f"({res['sec']}s, rc={res['rc']})", flush=True)


if __name__ == "__main__":
    main()
