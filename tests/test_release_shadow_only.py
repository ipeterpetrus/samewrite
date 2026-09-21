#!/usr/bin/env python3
"""The 1.4.x releases ship evidence acquisition and shadow evaluation — and nothing that writes.

A version bump is the cheapest possible place to activate something by accident: a flag defaults
differently, a module gets imported for its side effect, a shadow reporter grows one convenience
write. The README, the release notes and the manifests all say the CURRENT version and all say
promotion and candidate persistence are NOT active. This file is what makes that sentence
checkable instead of promised — and it reads the version from the manifest rather than naming
one, so a patch release cannot make this docstring quietly false.

Three questions, asked mechanically:

  INACTIVE    no v1.4 promotion or candidate-persistence entry point exists in the shipped tree.
  SILENT      the shadow reporter creates no file, no directory and no candidate — proved by
              running it over a real history and comparing the whole tree before and after.
  UNCOUPLED   the product version is metadata. No runtime module branches on it, so bumping it
              cannot turn behaviour on.

Standalone: run this file."""
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import carry                                                            # noqa: E402
from test_evidence_phase2 import facts                                  # noqa: E402

P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


def tree(path):
    """Every entry under a directory, by content AND metadata.

    Sizes are not enough: a rewrite of the same length would look identical, and "the reporter
    wrote nothing" is exactly the claim this release makes in public. A permission or mtime change
    is not a file write, but it is still a change to the tree, so it is captured too.
    """
    out = {}
    for base, dirs, files in os.walk(path):
        for name in dirs:
            st = os.stat(os.path.join(base, name))
            out[os.path.relpath(os.path.join(base, name), path)] = ("dir", st.st_mode)
        for name in files:
            full = os.path.join(base, name)
            st = os.stat(full)
            with open(full, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            # Content, permissions and mtime. NOT atime: reading a file updates it on many
            # filesystems, so an atime check would fail the reporter for doing its job.
            out[os.path.relpath(full, path)] = (digest, st.st_mode, st.st_mtime_ns)
    return out


def main():
    version = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))["version"]
    print(f"product version: {version}\n")

    # ------------------------------------------------------------------ INACTIVE
    tools = os.path.join(ROOT, "tools")
    shipped = sorted(f for f in os.listdir(tools) if f.endswith(".py"))
    check("no promotion module ships in this release", "evidence_promote.py" in shipped, False)

    # The frozen kernel CONTAINS the promotion rule — that is correct and it is not the question.
    # The question is who calls it. A caller that decides and then writes is a promotion path;
    # the shadow reporter decides and prints.
    callers = []
    for name in shipped:
        src = open(os.path.join(tools, name), encoding="utf-8").read()
        if "evidence.promotion" in src or "promotable" in src:
            callers.append(name)
    check("only the shadow reporter consumes the promotion rule", callers, ["evidence_shadow.py"])

    writes = ("open", "makedirs", "mkdir", "replace", "rename", "link", "symlink", "write",
              "unlink", "remove", "rmdir", "mkstemp", "NamedTemporaryFile", "write_text",
              "write_bytes", "touch", "copy", "copy2", "copyfile", "copytree", "dump",
              "writelines", "truncate", "mknod", "mkfifo", "chmod", "fchmod", "lchmod",
              "utime", "chown", "fchown", "lchown", "setxattr", "removexattr")
    shadow_src = open(os.path.join(tools, "evidence_shadow.py"), encoding="utf-8").read()
    found = sorted({n.func.attr for n in ast.walk(ast.parse(shadow_src))
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in writes} |
                   {n.func.id for n in ast.walk(ast.parse(shadow_src))
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id in writes})
    check("the shadow reporter calls no write primitive at all", found, [])

    # ------------------------------------------------------------------ SILENT
    workspace = tempfile.mkdtemp()
    history = os.path.join(workspace, "history.jsonl")
    for i in range(1, 4):
        f = facts(i)
        carry.history(history, f, sum(f["carry"].values()), scope_id="s")
    watched = os.path.join(workspace, "watched")       # a plausible candidate root, left empty
    os.makedirs(watched)

    before = tree(workspace)
    run = subprocess.run([sys.executable, os.path.join(tools, "evidence_shadow.py"), history,
                          "--scope", "s"], capture_output=True, text=True)
    after = tree(workspace)
    check("shadow exits 0 whatever it finds", run.returncode, 0)
    check("shadow reports the retained findings",
          all(name in run.stdout for name in ("listing_cost", "write_guard_retirement")), True)
    check("shadow changed nothing on disk", after, before)
    check("shadow wrote no candidate anywhere", os.listdir(watched), [])
    check("shadow says so in its own output", "no candidate written" in run.stdout, True)

    # The optimizer only writes proposals when a human asks for them by flag. Run it without one.
    before = tree(workspace)
    subprocess.run([sys.executable, os.path.join(tools, "optimize.py"), "--history", history,
                    "--ledger", os.path.join(workspace, "absent-ledger.jsonl"), "--scan"],
                   capture_output=True, text=True)      # --scan with no value: no live sweep
    check("the optimizer writes nothing without --emit-candidate", tree(workspace), before)

    # ------------------------------------------------------------------ UNCOUPLED
    # A runtime module that compares the product version could change behaviour when the manifest
    # is bumped. doctor.py may READ it (that is its job: report what is installed).
    branching = []
    for name in shipped:
        src = open(os.path.join(tools, name), encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Compare) and any(
                    isinstance(c, ast.Constant) and c.value in (version, "1.3.0")
                    for c in [node.left] + list(node.comparators)):
                branching.append(name)
    check("no runtime module branches on the product version", sorted(set(branching)), [])

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
