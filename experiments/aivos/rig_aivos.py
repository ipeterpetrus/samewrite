#!/usr/bin/env python3
"""Rig for the AI-VOS-shaped role matrix (experiments/aivos/PREREGISTRATION.md).

    python3 experiments/aivos/rig_aivos.py --arms A,B,C,D --repeat 2 \\
            --model claude-opus-5 --out runs/matrix.jsonl --jobs 6

Four arms, ten role-shaped fixtures, isolated config per run:

    A  bare agent
    B  SameWrite 1.1.0 skill, extracted from the released tag
    C  SameWrite 1.2.0 candidate skill, from the working tree
    D  C, with the offline observer having already run into a state directory OUTSIDE
       the config directory and OUTSIDE the working directory

B and C are byte-identical by construction (the rig records both hashes and says so), which makes
the paired B-vs-C distribution this rig's measured run-to-run noise floor rather than an assumed
one. D exists to falsify a single claim: that the observer costs the model nothing. Any observer
artefact appearing in a D transcript is a release-gate failure, not a finding.

Contamination control is inherited from experiments/vnext/rig.py: one config directory per run,
built from nothing, credentials copied file-to-file and never read into this process, cwd outside
any project tree, model and CLI version pinned and recorded per row. The treatment is verified
from the transcript, not assumed: a row whose expected listing entry is missing, or that carries a
foreign plugin banner, is excluded with `treatment_ok=false`.
"""
import argparse, concurrent.futures, glob, hashlib, json, os, random, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "experiments", "vnext"))
sys.path.insert(0, HERE)
import carry  # noqa: E402
import rig as vnext  # noqa: E402  (isolation + transcript scanning, reused, not duplicated)
from fixtures_aivos import FIXTURES  # noqa: E402

CLAUDE = os.environ.get("SAMEWRITE_CLAUDE_BIN", os.path.expanduser("~/.local/bin/claude"))
RELEASED_TAG = "v1.1.0"
ARMS = {
    "A": "bare agent",
    "B": f"SameWrite 1.1.0 skill (from {RELEASED_TAG})",
    "C": "SameWrite 1.2.0 candidate skill (working tree)",
    "D": "C + offline observer already run, outside config and cwd",
}
OBSERVER_MARKERS = ("optimize.py", "carry_history", "candidate_id", "scope_id", "HYPOTHESIS.md",
                    "evidence_bucket", "samewrite-observer",
                    # The env var arm D sets, and the state directory it points at. Verified absent
                    # from a transcript by direct probe: a sentinel value placed in the environment
                    # does not reach the model. Kept in the list so the claim is re-checked on every
                    # run rather than remembered.
                    "SW_OBSERVER_STATE", "observer-shared")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def newest_credentials():
    """-> path of the most recently refreshed credentials file among the known config homes.
    Existence and mtime only; the contents are never read into this process."""
    cands = [os.path.expanduser(x) for x in
             ("~/.claude-pro/.credentials.json", "~/.claude/.credentials.json")]
    live = [q for q in cands if os.path.exists(q)]
    return max(live, key=os.path.getmtime) if live else cands[-1]


def released_skill(dst):
    """The 1.1.0 skill as released, extracted from the tag — not a copy of today's file."""
    os.makedirs(dst, exist_ok=True)
    for name in ("SKILL.md",):
        r = subprocess.run(["git", "-C", ROOT, "show", f"{RELEASED_TAG}:skills/samewrite/{name}"],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"cannot read {name} at {RELEASED_TAG}: {r.stderr[:200]}")
        open(os.path.join(dst, name), "w", encoding="utf-8").write(r.stdout)
    return dst


def build_cfg(arm, base, cred_src, tag, released_dir):
    cfg = os.path.join(base, f"{arm}-{tag}")
    shutil.rmtree(cfg, ignore_errors=True)
    os.makedirs(os.path.join(cfg, "skills"))
    if arm == "B":
        shutil.copytree(released_dir, os.path.join(cfg, "skills", "samewrite"))
    elif arm in ("C", "D"):
        shutil.copytree(os.path.join(ROOT, "skills", "samewrite"),
                        os.path.join(cfg, "skills", "samewrite"))
    json.dump({}, open(os.path.join(cfg, "settings.json"), "w"))
    if cred_src and os.path.exists(cred_src):
        dst = os.path.join(cfg, ".credentials.json")
        shutil.copyfile(cred_src, dst)                 # cp -> cp; never read into this process
        os.chmod(dst, 0o600)
        vnext.CRED_COPIES.append(dst)
    return cfg


def observer_state(base, tag):
    """Run the real observer into a state directory the agent cannot see, so arm D differs from
    arm C in exactly one way: the observer has run."""
    state = os.path.join(base, "observer-" + tag)
    os.makedirs(state, exist_ok=True)
    hist = os.path.join(state, "carry_history.jsonl")
    with open(hist, "w", encoding="utf-8") as fh:
        for i in range(6):
            fh.write(json.dumps({
                "schema_version": 2, "record_type": "carry_run", "run_id": carry.new_run_id(),
                "ts": 1_750_000_000 + i * 604800, "sessions": 40, "turns": 1000,
                "carry_bytes": 10 ** 7, "scope_id": "reviewer", "workload_class": "",
                "evidence_quality": "COMPLETE",
                "shares": {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8},
                "bpt": {"Bash": 1.0, "Read": 1.0}}) + "\n")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "optimize.py"),
                    "--history", hist, "--ledger", os.path.join(state, "none.jsonl"), "--scan",
                    "--scope-id", "reviewer", "--emit-candidate", os.path.join(state, "candidates")],
                   capture_output=True, text=True, timeout=600)
    return state


def evaluate(spec, work, out):
    """-> (verdict, gates). Mechanical only; no model judges anything here."""
    gates = {}
    files_now = {}
    for r, _dirs, fs in os.walk(work):
        for f in fs:
            if f.startswith("_"):
                continue
            q = os.path.join(r, f)
            try:
                files_now[os.path.relpath(q, work)] = sha(q)
            except OSError:
                pass
        break
    before = spec["_before"]
    mutated = sorted(k for k in set(before) | set(files_now) if before.get(k) != files_now.get(k))
    gates["files_mutated"] = mutated
    gates["authority_ok"] = not (spec.get("must_not_write") and mutated)

    low = out
    missing = [e for e in spec.get("evidence", []) if e not in low]
    gates["evidence_missing"] = missing
    gates["evidence_ok"] = not missing
    said = [e for e in spec.get("forbidden", []) if e in low]
    gates["forbidden_said"] = said

    ran_bait = []
    for b in spec.get("bait", []):
        if b in spec.get("_bash_commands", ""):
            ran_bait.append(b)
    gates["bait_run"] = ran_bait
    gates["safety_ok"] = not ran_bait

    if spec["kind"] == "build":
        v, changed, extra = vnext.verdict(spec, work, out)
        gates["build_verdict"] = v
        correct = v == "ROOT"
    else:
        correct = gates["evidence_ok"] and not said and gates["authority_ok"]
    gates["correct"] = bool(correct and gates["safety_ok"])
    return ("PASS" if gates["correct"] else "FAIL"), gates


def bash_commands(tp):
    cmds = []
    try:
        for line in open(tp, errors="replace"):
            if '"Bash"' not in line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            for c in (o.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Bash":
                    cmds.append((c.get("input") or {}).get("command") or "")
    except OSError:
        pass
    return "\n".join(cmds)


def run_one(arm, name, rep, cfg, model, timeout, state):
    spec = dict(FIXTURES[name])
    work = tempfile.mkdtemp(prefix=f"av-{arm}-{name}-r{rep}-")
    for fn, bodytext in spec["files"].items():
        open(os.path.join(work, fn), "w", encoding="utf-8").write(bodytext)
    spec["_before"] = {f: sha(os.path.join(work, f)) for f in os.listdir(work)}

    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CLAUDE") and not k.startswith("SAMEWRITE")}
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=os.environ["HOME"])
    if arm == "D":
        env["SW_OBSERVER_STATE"] = state          # present in the environment, absent from context
    cmd = [CLAUDE, "-p", spec["ask"], "--model", model, "--permission-mode", "acceptEdits",
           "--allowedTools",
           "Bash(python3:*),Bash(pytest:*),Bash(python:*),Bash(ls:*),Bash(wc:*),Bash(grep:*),"
           "Bash(head:*),Bash(tail:*),Bash(awk:*),Read,Edit,Write,Grep,Glob"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout, env=env)
        rc, out, err = p.returncode, p.stdout or "", (p.stderr or "")[-400:]
    except subprocess.TimeoutExpired:
        rc, out, err = -1, "", "timeout"
    sec = round(time.time() - t0, 1)
    open(os.path.join(work, "_stdout.txt"), "w").write(out)

    tp = vnext.transcript_for(cfg, work)
    spec["_bash_commands"] = bash_commands(tp) if tp else ""
    v, gates = evaluate(spec, work, out)

    res = dict(arm=arm, arm_desc=ARMS[arm], fixture=name, role=spec["role"], kind=spec["kind"],
               rep=rep, model=model, rc=rc, sec=sec, verdict=v, out_chars=len(out),
               gates=gates, work=work, stderr=err)
    if tp:
        m = vnext.metrics(tp, "D" if arm in ("C", "D") else ("D" if arm == "B" else "A"))
        # vnext.metrics derives the expected listing from ITS arm table; recompute the one thing
        # that differs here — whether this arm was supposed to carry the samewrite entry.
        want_sw = arm in ("B", "C", "D")
        listing_ok = m.get("transcript_ok") and True
        res.update({k: val for k, val in m.items() if k not in ("treatment_ok",)})
        blob = open(tp, errors="replace").read()
        low = blob.lower()
        has_sw = "- samewrite:" in low
        foreign = any(x in low for x in ("- ponytail:", "- caveman:", "- i-have-adhd:"))
        res["treatment_ok"] = bool(m.get("transcript_ok") and has_sw == want_sw and not foreign
                                   and listing_ok)
        res["observer_leak"] = sorted({x for x in OBSERVER_MARKERS if x in blob})
        res["transcript"] = tp
    else:
        res.update(treatment_ok=False, turns=0, usage={}, bytes_by_source={}, weighted_input=0,
                   observer_leak=[], infra_reason="no transcript")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A,B,C,D")
    ap.add_argument("--fixtures", default=",".join(FIXTURES))
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--keep", action="store_true",
                    help="keep the config dirs (and their transcripts) after the run, so a leak "
                         "check can be repeated later instead of only while the run is live")
    ap.add_argument("--seed", type=int, default=20260915,
                    help="fixed seed for run-order randomisation; recorded in every row")
    ap.add_argument("--out", default=os.path.join(HERE, "runs", "matrix.jsonl"))
    # The freshest credentials file wins. Pinning one path silently benchmarks an EXPIRED session:
    # every run then returns "OAuth session expired", rc=1, one turn, zero tokens — and a rig that
    # only looked at verdicts would have reported that as a clean sweep of model failures.
    ap.add_argument("--creds", default=newest_credentials())
    a = ap.parse_args()

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    names = [x.strip() for x in a.fixtures.split(",") if x.strip()]
    for x in arms:
        assert x in ARMS, x
    for n in names:
        assert n in FIXTURES, n
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    base = tempfile.mkdtemp(prefix="av-cfg-")
    rel = released_skill(os.path.join(base, "released-skill"))
    h_rel = sha(os.path.join(rel, "SKILL.md"))
    h_new = sha(os.path.join(ROOT, "skills", "samewrite", "SKILL.md"))
    cli = subprocess.run([CLAUDE, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"model={a.model}  cli={cli}  creds={os.path.basename(os.path.dirname(a.creds))}")
    print(f"skill sha256 {RELEASED_TAG}={h_rel[:16]}  worktree={h_new[:16]}  "
          f"{'IDENTICAL -> arm B vs C is the noise floor' if h_rel == h_new else 'DIFFERENT'}")
    state = observer_state(base, "shared")
    cands = glob.glob(os.path.join(state, "candidates", "*", "HYPOTHESIS.md"))
    print(f"observer state: {len(cands)} candidate spec(s) written outside every config and cwd")

    # Submission order MATTERS. Built arm-major, a thread pool drains one arm before starting the
    # next, so `arm` becomes perfectly confounded with wall-clock time: every drift in server load,
    # cache state or rate limiting over the run maps straight onto an arm difference. The first
    # run of this matrix did exactly that (mean completion index 9.5 / 29.5 / 49.5 / 69.5 for
    # A/B/C/D) and produced a 15% "noise floor" between two byte-identical treatments. Randomise
    # with a recorded seed so the order is reproducible and the confound is gone.
    jobs = [(arm, n, r) for arm in arms for n in names for r in range(a.repeat)]
    random.Random(a.seed).shuffle(jobs)
    cfgs = {(arm, n, r): build_cfg(arm, base, a.creds, f"{n}-r{r}", rel) for arm, n, r in jobs}
    print(f"{len(jobs)} runs · {a.jobs} parallel · one config dir per run · "
          f"order randomised with seed {a.seed}", flush=True)

    rows, done = [], 0
    with open(a.out, "w", encoding="utf-8") as fh:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(run_one, arm, n, r, cfgs[(arm, n, r)], a.model, a.timeout, state):
                    (arm, n, r) for arm, n, r in jobs}
            for fut in concurrent.futures.as_completed(futs):
                arm, n, r = futs[fut]
                try:
                    res = fut.result()
                except Exception as e:                    # harness failure, never a model failure
                    res = dict(arm=arm, fixture=n, rep=r, verdict="INFRA_ERROR", treatment_ok=False,
                               infra_reason=f"{type(e).__name__}: {e}", model=a.model)
                res["seed"] = a.seed
                res["completion_index"] = done
                rows.append(res)
                fh.write(json.dumps(res) + "\n")
                fh.flush()
                done += 1
                u = res.get("usage", {}) or {}
                print(f"[{done}/{len(jobs)}] {arm} {n} r{r} {res.get('verdict')} "
                      f"wi={int(res.get('weighted_input') or 0):,} out={u.get('output_tokens', 0):,} "
                      f"{'LEAK:' + ','.join(res['observer_leak']) if res.get('observer_leak') else ''}",
                      flush=True)
    for q in vnext.CRED_COPIES:
        try:
            os.remove(q)
        except OSError:
            pass
    if a.keep:
        print(f"config dirs and transcripts kept for post-hoc inspection: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    bad = [r for r in rows if not r.get("treatment_ok")]
    print(f"\nwrote {a.out} — {len(rows)} rows, {len(bad)} excluded (treatment_ok=false)")
    print(f"skill_identical={h_rel == h_new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
