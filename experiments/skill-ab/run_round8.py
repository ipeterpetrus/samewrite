#!/usr/bin/env python3
"""Ronde 8: ponytail pada tugas BESAR. Gerbang benar dulu, baru ukur ukuran perubahan."""
import argparse, ast, json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures8 as fx
from rig_modes import defs_count, CFG, ONELINER

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.local/bin/claude")


def imports_count(src):
    try:
        return sum(1 for n in ast.walk(ast.parse(src))
                   if isinstance(n, (ast.Import, ast.ImportFrom)))
    except SyntaxError:
        return -1


def one(name, arm, model, timeout):
    spec = fx.F[name]
    work = tempfile.mkdtemp(prefix=f"p8-{name}-{arm}-")
    d = fx.build(work, name)
    base = spec["files"]["mod.py"]
    cfg = os.path.join(HERE, CFG["ponytail" if arm == "mode" else arm])
    prompt = spec["ask"]
    if arm == "oneline":
        prompt = ONELINER["ponytail"] + " " + prompt
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
    t0 = time.time()
    try:
        p = subprocess.run([CLAUDE, "-p", prompt, "--model", model,
                            "--permission-mode", "acceptEdits"],
                           cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
        rc = p.returncode
        open(os.path.join(d, "_stdout.txt"), "w").write(p.stdout or "")
    except subprocess.TimeoutExpired:
        rc = -1
    ok = subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", "test_target.py"],
                        cwd=d, capture_output=True, timeout=240).returncode
    mp = os.path.join(d, "mod.py")
    cur = open(mp).read() if os.path.exists(mp) else ""
    extra = [f for f in os.listdir(d) if f.endswith(".py")
             and f not in spec["files"] and not f.startswith(("_", "test_"))]
    return dict(fixture=name, arm=arm, rc=rc, sec=round(time.time() - t0, 1),
                work=work, passing=(ok == 0),
                lines=len([l for l in cur.splitlines() if l.strip()]),
                added=max(0, len(cur.splitlines()) - len(base.splitlines())),
                defs=defs_count(cur), new_defs=max(0, defs_count(cur) - defs_count(base)),
                imports=imports_count(cur), new_files=len(extra))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--arms", default="plain,oneline,mode")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for r in range(a.repeat):
        for n in sorted(fx.F):
            for arm in a.arms.split(","):
                res = one(n, arm, a.model, a.timeout)
                res.update(rep=r, model=a.model)
                with open(a.out, "a") as fh:
                    fh.write(json.dumps(res) + "\n")
                print(f"{n:16s} {arm:8s} rep{r} rc={res['rc']} {res['sec']}s "
                      f"pass={res['passing']} baris={res['lines']:>3} def={res['defs']:>2} "
                      f"impor={res['imports']} berkas_baru={res['new_files']}", flush=True)


if __name__ == "__main__":
    main()
