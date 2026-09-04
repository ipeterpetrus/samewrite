#!/usr/bin/env python3
"""Pick fixtures out of MBPP by a mechanical rule, so the author never chooses one.

MBPP (Austin et al. 2021, google-research, CC-BY-4.0) ships a prompt, a reference
solution and behaviour-pinning asserts for 974 tasks, all written years before this
hypothesis existed. The selection rule below touches only the reference solution and
its own tests - never any arm of any experiment - so it can be run before, during or
after the study and give the same 20 tasks."""
import ast, json, os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "mbpp.jsonl")
SHA = "ccf64ceae9c5403bf50a044cb6d505bfd2a2963ee58338ba268fd65beab92a9f"
URL = ("https://raw.githubusercontent.com/google-research/google-research/"
       "master/mbpp/mbpp.jsonl")
MIN_LINES = 12          # room to over-engineer; 120 of 974 tasks qualify
WANT = 20               # sign-test floor over 20 tasks is 2/2**20, tie-proof


def ensure_data():
    """The dataset is not vendored: it is fetched and checked against the hash the
    protocol was registered with. A different hash is a different experiment."""
    import hashlib, urllib.request
    if not os.path.exists(DATA):
        urllib.request.urlretrieve(URL, DATA)
    got = hashlib.sha256(open(DATA, "rb").read()).hexdigest()
    if got != SHA:
        raise SystemExit(f"mbpp.jsonl hash {got} != registered {SHA}")
    return DATA


def nonblank(src):
    return len([l for l in src.replace("\r", "").split("\n") if l.strip()])


def stdlib_only(src):
    """Reject anything importing a third-party package: the run must not depend on
    what happens to be installed."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    ok = {"math", "re", "itertools", "collections", "functools", "heapq", "bisect",
          "string", "sys", "os", "datetime", "operator", "random", "cmath", "copy"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            if any(a.name.split(".")[0] not in ok for a in n.names):
                return False
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] not in ok:
                return False
    return True


def build(root, row):
    """One task directory: an empty module for the agent to fill, and the dataset's
    own asserts as the test file."""
    d = os.path.join(root, f"mbpp_{row['task_id']}")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "mod.py"), "w").write("")
    setup = row.get("test_setup_code") or ""
    body = "\n".join("    " + t for t in row["test_list"])
    open(os.path.join(d, "test_target.py"), "w").write(
        "from mod import *\n" + (setup + "\n" if setup else "") +
        "\ndef test_reference_behaviour():\n" + body + "\n")
    return d


def canonical_passes(row):
    """Positive control, free and author-independent: write the DATASET's own solution
    and require its own tests to go green. A task whose reference fails is unusable and
    is dropped by the rule, not by judgement."""
    with tempfile.TemporaryDirectory() as root:
        d = build(root, row)
        open(os.path.join(d, "mod.py"), "w").write(row["code"].replace("\r", ""))
        r = subprocess.run(["/usr/bin/python3", "-m", "pytest", "-q", "test_target.py"],
                           cwd=d, capture_output=True, timeout=120)
        return r.returncode == 0


def selected():
    rows = [json.loads(l) for l in open(ensure_data())]
    out = []
    for row in sorted(rows, key=lambda r: r["task_id"]):
        if nonblank(row["code"]) < MIN_LINES:
            continue
        if not stdlib_only(row["code"]):
            continue
        if not canonical_passes(row):
            continue
        out.append(row)
        if len(out) == WANT:
            break
    return out


if __name__ == "__main__":
    sel = selected()
    print(f"{len(sel)} tasks selected")
    for r in sel:
        print(f"  {r['task_id']:4d}  {nonblank(r['code']):2d} lines  {r['text'][:66]}")
