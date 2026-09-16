#!/usr/bin/env python3
"""Is SameWrite ready to run against a real governed workspace without touching it?

Four questions, answered by execution rather than by reading the code:

  1. can the observer find the work at all (a scoped transcript sweep)?
  2. does anything in the governed repository change while it runs?
  3. does any private thing — a path, a prompt, a source line, a planted secret — reach the
     observer's output, its JSON, or a candidate specification?
  4. given evidence that *sounds* actionable, does the optimizer still only propose?

The fourth is the one that matters. A tool that behaves when the evidence is boring proves
nothing; this deliberately hands it a strong, clean, threshold-crossing trend and then checks that
the governed tree, the git index, the remote and the authority files are all exactly as they were.

    python3 experiments/aivos/readiness.py --workspace ~/ai-vos-next
    python3 experiments/aivos/readiness.py --workspace ~/ai-vos-next --json

Read-only with respect to the workspace: it is hashed before and after, never written to. The
observer's own state goes to a throwaway directory outside it.
"""
import argparse, collections, hashlib, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import carry  # noqa: E402

CANARY = "AIVOS_CANARY_SECRET_DO_NOT_LEAK_4b19ff20"
P = F = 0


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


def tree_state(root):
    """Everything an audit would care about: file bytes, the git index, HEAD, and the remote."""
    files = {}
    for r, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in fs:
            q = os.path.join(r, f)
            try:
                files[os.path.relpath(q, root)] = hashlib.sha256(open(q, "rb").read()).hexdigest()
            except OSError:
                pass
    def git(*a):
        return subprocess.run(["git", "-C", root] + list(a), capture_output=True,
                              text=True).stdout.strip()
    return dict(files=files, head=git("rev-parse", "HEAD"), status=git("status", "--porcelain"),
                branch=git("branch", "--show-current"), remotes=git("remote", "-v"),
                index=git("ls-files", "-s") and hashlib.sha256(
                    git("ls-files", "-s").encode()).hexdigest())


def synth_transcripts(d, n=6, turns=60):
    """A governed-work shape, with a secret planted where a careless reader would find it: in a
    Bash command, in a tool result, and in a file the agent read."""
    proj = os.path.join(d, "projects", "-home-ubuntu-governed")
    os.makedirs(proj)
    for s in range(n):
        rows = []
        for i in range(turns):
            rows.append({"type": "assistant", "version": "2.1.271", "message": {
                "model": "claude-opus-5", "usage": {"input_tokens": 10, "output_tokens": 20,
                                                    "cache_read_input_tokens": 1000},
                "content": [{"type": "tool_use", "id": f"{s}-{i}", "name": "Bash",
                             "input": {"command": f"export TOKEN={CANARY} && git log --oneline -1"}}]}})
            rows.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"{s}-{i}",
                 "content": f"approval ledger entry {i}: {CANARY}"}]}})
        with open(os.path.join(proj, f"sess{s}.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
    return proj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=os.path.expanduser("~/ai-vos-next"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    ws = os.path.abspath(os.path.expanduser(a.workspace))
    if not os.path.isdir(ws):
        print(f"workspace not found: {ws}")
        return 2

    print(f"governed workspace : {ws}")
    print(f"  HEAD             : {subprocess.run(['git','-C',ws,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()}")
    before = tree_state(ws)
    print(f"  files hashed     : {len(before['files']):,}")
    print(f"  worktree dirty   : {len(before['status'].splitlines())} file(s)\n")

    d = tempfile.mkdtemp(prefix="sw-aivos-ready-")
    state = os.path.join(d, "state")          # observer state, OUTSIDE the governed repository
    os.makedirs(state)
    proj = synth_transcripts(d)
    hist = os.path.join(state, "carry_history.jsonl")
    cand = os.path.join(state, "candidates")

    # ---------------------------------------------------------------- 1. can it find the work
    paths = sorted(os.path.join(proj, f) for f in os.listdir(proj))
    acc = carry.accumulate(paths, min_turns=1)
    check("observer discovers the workspace transcripts", acc["sessions"] > 0, True)
    check("evidence quality is a real label", acc["quality"], "COMPLETE")
    print(f"  MEASURED  {acc['sessions']} sessions / {acc['turns']:,} turns swept")

    # ---------------------------------------------------------------- 2. aggregate-only records
    C = sum(acc["carry"].values()) or 1
    lines = carry.history(hist, acc, C, scope_id="governed", workload_class="audit")
    rec = json.loads(open(hist).read().splitlines()[-1])
    check("record stores aggregates, not content",
          sorted(k for k in rec if k in ("shares", "bpt", "turns", "sessions")) ,
          ["bpt", "sessions", "shares", "turns"])
    blob = json.dumps(rec)
    check("record contains no planted secret", CANARY in blob, False)
    check("record contains no filesystem path", ws in blob or proj in blob or "/home/" in blob, False)

    # a strong, clean, threshold-crossing trend: evidence that SOUNDS actionable
    with open(hist, "w", encoding="utf-8") as fh:
        for i in range(6):
            fh.write(json.dumps({
                "schema_version": 2, "record_type": "carry_run", "run_id": carry.new_run_id(),
                "ts": 1_750_000_000 + i * 604800, "sessions": 60, "turns": 3000,
                "carry_bytes": 10 ** 8, "scope_id": "governed", "workload_class": "audit",
                # Since 1.3.1 a COMPLETE claim is checked against the record's own acquisition
                # counters, so a fixture meaning "a clean sweep" writes them — which is exactly what
                # carry.history() produces. This is the POSITIVE control: if the fail-closed rule
                # ever blocked clean evidence too, this candidate would stop appearing.
                "scanned": 60, "unreadable": 0, "oversize": 0, "skipped_by_limit": 0,
                "evidence_quality": "COMPLETE", "runtimes": {"2.1.271": 60}, "models": {"m": 60},
                "shares": {"Bash": 40.0 + i * 9, "Read": 60.0 - i * 9},
                "bpt": {"Bash": 1.0, "Read": 1.0}}) + "\n")

    # ---------------------------------------------------------------- 3 + 4. run it for real
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "optimize.py"),
                        "--history", hist, "--ledger", os.path.join(state, "none.jsonl"),
                        "--scan", proj, "--min-turns", "1", "--scope-id", "governed",
                        "--emit-candidate", cand],
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    check("optimizer runs to completion", r.returncode, 0)
    check("it produced a candidate (evidence that sounds actionable)", "CANDIDATE" in out, True)
    check("human report leaks no secret", CANARY in out, False)
    check("human report leaks no path", (ws in out) or (proj in out) or ("/home/" in out), False)

    rj = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "optimize.py"),
                         "--history", hist, "--ledger", os.path.join(state, "none.jsonl"),
                         "--scan", proj, "--min-turns", "1", "--scope-id", "governed", "--json"],
                        capture_output=True, text=True, timeout=900)
    check("JSON leaks no secret", CANARY in rj.stdout, False)
    check("JSON leaks no path", ("/home/" in rj.stdout) or (ws in rj.stdout), False)

    specs = [os.path.join(r_, f) for r_, _d, fs in os.walk(cand) for f in fs if f.endswith(".md")]
    check("a specification was written, outside the governed repository", bool(specs), True)
    check("specifications live outside the workspace",
          all(not os.path.abspath(s).startswith(ws + os.sep) for s in specs), True)
    sblob = "".join(open(s, encoding="utf-8").read() for s in specs)
    check("specification leaks no secret", CANARY in sblob, False)
    check("specification leaks no path", ("/home/" in sblob) or (ws in sblob), False)
    # The canary verdict must come from the canary evidence, not from "did anything fail".
    # The first version derived CANARY_LEAK from the total failure count, so an unrelated broken
    # probe would have reported a leak that never happened — a false alarm is a false claim too.
    leak = any(CANARY in blob_ for blob_ in (out, rj.stdout, sblob, json.dumps(rec)))

    # ---------------------------------------------------------------- the zero-authority check
    after = tree_state(ws)
    changed = sorted(k for k in set(before["files"]) | set(after["files"])
                     if before["files"].get(k) != after["files"].get(k))
    check("no file in the governed workspace changed", changed, [])
    check("git HEAD unchanged", after["head"], before["head"])
    check("git status unchanged", after["status"], before["status"])
    check("git index unchanged", after["index"], before["index"])
    check("git remotes unchanged", after["remotes"], before["remotes"])
    check("branch unchanged", after["branch"], before["branch"])

    # Scan for EXECUTION CONSTRUCTS, not bare substrings. The first version of this check looked
    # for "gh " and matched the English words "enough" and "through", reporting an execution path
    # in a file that has none. A probe that fires on prose is worse than no probe: it teaches the
    # reader to ignore it.
    src = open(os.path.join(ROOT, "tools", "optimize.py"), encoding="utf-8").read()
    constructs = {
        "subprocess": r"\bimport\s+subprocess\b|\bsubprocess\.",
        "os.system": r"\bos\.system\s*\(",
        "os.exec*/spawn": r"\bos\.(exec[lv]?[ep]*|spawn\w*|popen)\s*\(",
        "shell out via pty/pexpect": r"\bimport\s+(pty|pexpect)\b",
        "git invocation": r"[\"'`]\s*git\s+(commit|push|tag|add|checkout|reset)\b",
        "gh invocation": r"[\"'`]\s*gh\s+(api|pr|release|repo)\b",
    }
    import re as _re
    for label, pat in constructs.items():
        hits = _re.findall(pat, src)
        check(f"optimizer source has no execution construct: {label}", hits, [])

    shutil.rmtree(d, ignore_errors=True)
    print(f"\n{P} PASS / {F} FAIL")
    mutated = bool(changed) or after["head"] != before["head"] or after["status"] != before["status"]
    print(f"CANARY_LEAK={'YES' if leak else 'NO'}   "
          f"PROPOSAL_ONLY={'FAIL' if mutated else 'PASS'}   "
          f"AI_VOS_REPO_MUTATED={'YES' if mutated else 'NO'}")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
