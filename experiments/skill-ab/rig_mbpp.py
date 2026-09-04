#!/usr/bin/env python3
"""Minimal-change instruction on third-party frozen tasks (MBPP).

Nothing here was written by the author of the hypothesis: the prompts, the reference
solutions and the tests all ship with the dataset, and the twenty tasks are chosen by
the mechanical rule in mbpp_select.py. Protocol: PREREGISTRATION_mbpp_minimal_change.md
"""
import argparse, json, os, subprocess, tempfile, time
import mbpp_select as sel

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.local/bin/claude")

ONELINER = "Make the change as small as possible; do not add abstractions that were not asked for."


def one(row, arm, model, timeout, cfg):
    work = tempfile.mkdtemp(prefix=f"mb-{row['task_id']}-{arm}-")
    d = sel.build(work, row)
    prompt = (row["text"].strip() + " Put it in mod.py. test_target.py must pass.")
    if arm == "oneline":
        prompt = ONELINER + " " + prompt
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg)
    t0 = time.time()
    try:
        p = subprocess.run([CLAUDE, "-p", prompt, "--model", model,
                            "--permission-mode", "acceptEdits"],
                           cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        rc = -1
    gate = subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", "test_target.py"],
                          cwd=d, capture_output=True, timeout=240).returncode
    mp = os.path.join(d, "mod.py")
    src = open(mp).read() if os.path.exists(mp) else ""
    extra = [f for f in os.listdir(d) if f.endswith(".py")
             and f not in ("mod.py", "test_target.py") and not f.startswith("_")]
    return dict(task_id=row["task_id"], arm=arm, rc=rc, sec=round(time.time() - t0, 1),
                passing=(gate == 0), lines=sel.nonblank(src), chars=len(src.strip()),
                new_files=len(extra), work=work,
                reference_lines=sel.nonblank(row["code"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="plain,oneline")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--cfg", default=os.path.join(HERE, "cfg_plain"))
    ap.add_argument("--limit", type=int, default=0, help="0 = all selected tasks")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = sel.selected()
    if a.limit:
        rows = rows[:a.limit]
    for row in rows:
        for arm in a.arms.split(","):
            r = one(row, arm, a.model, a.timeout, a.cfg)
            r.update(model=a.model)
            with open(a.out, "a") as fh:
                fh.write(json.dumps(r) + "\n")
            print(f"mbpp_{r['task_id']:<4d} {arm:8s} rc={r['rc']} {r['sec']:>5}s "
                  f"pass={str(r['passing']):5s} lines={r['lines']:>3} chars={r['chars']:>4} "
                  f"ref={r['reference_lines']:>2} new_files={r['new_files']}", flush=True)


if __name__ == "__main__":
    main()
