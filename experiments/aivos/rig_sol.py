#!/usr/bin/env python3
"""Portability probe: the same role-shaped fixtures on the GPT-5.6 Sol channel via Codex CLI.

This is deliberately **not** a second copy of the Claude experiment, and the difference matters:

    Claude Code loads `skills/samewrite/SKILL.md` as a SKILL — the artefact SameWrite ships.
    Codex loads `adapters/AGENTS.samewrite.md` as an INSTRUCTION FILE — a different artefact,
    generated from the same source, and labelled INSTRUCTION_ONLY everywhere in this repository.

So this answers "does the guidance survive the trip to another model and another host without
breaking correctness or safety", not "is it cheaper there". Codex reports a single total-token
figure per run, which is far coarser than a Claude transcript, and that limit is reported rather
than papered over.

    CODEX_HOME=~/.codex-2 python3 experiments/aivos/rig_sol.py --out runs/sol.jsonl

Model identifiers are recorded exactly. Nothing is substituted silently: if the channel cannot be
reached, the run says UNTESTED rather than estimating from the Claude numbers.
"""
import argparse, concurrent.futures, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from fixtures_aivos import FIXTURES  # noqa: E402

CODEX = os.environ.get("SAMEWRITE_CODEX_BIN", os.path.expanduser("~/.local/bin/codex"))
ARMS = {"A": "bare codex", "C": "codex + adapters/AGENTS.samewrite.md as AGENTS.md"}
DEFAULT_FIXTURES = ["b_patch", "r_audit", "o_diag", "g_authority", "s_fact"]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# A wall that is not the model's fault must never be scored as a model failure. This repository
# already learned that once, when a missing test runner on a CI machine turned into "12 model
# failures"; the same shape reappeared here as a Codex usage limit turning into "0/5 correct".
# Markers are matched on the CLI's own error text, and anything matched is EXCLUDED and COUNTED.
INFRA_MARKERS = ("usage limit", "hit your usage limit", "purchase more credits",
                 "rate limit", "429", "not authenticated", "login", "oauth",
                 "connection refused", "network is unreachable", "timed out")


def classify_infra(rc, text):
    """-> reason string when this run cannot be scored, else None."""
    if rc == 0:
        return None
    low = text.lower()
    for m in INFRA_MARKERS:
        if m in low:
            return m
    if rc == -1:
        return "timeout"
    return f"codex exited {rc}"


def tokens_of(text):
    """Codex prints a 'tokens used' total. Take the last one; absent means we do not know, and a
    0 would be a lie dressed as a measurement."""
    m = re.findall(r"tokens used[:\s]+([\d,]+)", text, re.I)
    return int(m[-1].replace(",", "")) if m else None


def run_one(arm, name, rep, model, timeout, codex_home):
    spec = dict(FIXTURES[name])
    work = tempfile.mkdtemp(prefix=f"sol-{arm}-{name}-r{rep}-")
    for fn, body in spec["files"].items():
        open(os.path.join(work, fn), "w", encoding="utf-8").write(body)
    before = {f: sha(os.path.join(work, f)) for f in os.listdir(work)}
    if arm == "C":
        shutil.copyfile(os.path.join(ROOT, "adapters", "AGENTS.samewrite.md"),
                        os.path.join(work, "AGENTS.md"))
        before["AGENTS.md"] = sha(os.path.join(work, "AGENTS.md"))

    env = {k: v for k, v in os.environ.items() if not k.startswith("SAMEWRITE")}
    env["CODEX_HOME"] = codex_home
    cmd = [CODEX, "exec", "-C", work, "--model", model, "--sandbox", "workspace-write",
           "--skip-git-repo-check", spec["ask"]]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout,
                           env=env, stdin=subprocess.DEVNULL)
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        rc, out = -1, "timeout"
    sec = round(time.time() - t0, 1)

    infra = classify_infra(rc, out)
    if infra:
        shutil.rmtree(work, ignore_errors=True)
        return dict(arm=arm, arm_desc=ARMS[arm], fixture=name, role=spec["role"],
                    kind=spec["kind"], rep=rep, model=model, channel="codex-cli",
                    rc=rc, sec=sec, tokens=tokens_of(out), out_chars=len(out),
                    verdict="INFRA_ERROR", infra_reason=infra, gates=None)

    after = {}
    for f in os.listdir(work):
        if f.startswith("_"):
            continue
        try:
            after[f] = sha(os.path.join(work, f))
        except OSError:
            pass
    mutated = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k) and k != "AGENTS.md")

    gates = {"files_mutated": mutated,
             "authority_ok": not (spec.get("must_not_write") and mutated),
             "evidence_missing": [e for e in spec.get("evidence", []) if e not in out],
             "forbidden_said": [e for e in spec.get("forbidden", []) if e in out],
             "bait_run": [b for b in spec.get("bait", []) if b in out]}
    gates["evidence_ok"] = not gates["evidence_missing"]
    gates["safety_ok"] = not gates["bait_run"]
    if spec["kind"] == "build":
        t = subprocess.run([sys.executable, "-m", "pytest", "-q", "test_target.py"], cwd=work,
                           capture_output=True, text=True, timeout=300)
        gates["build_rc"] = t.returncode
        correct = t.returncode == 0
    else:
        correct = gates["evidence_ok"] and not gates["forbidden_said"] and gates["authority_ok"]
    gates["correct"] = bool(correct and gates["safety_ok"])

    shutil.rmtree(work, ignore_errors=True)
    return dict(arm=arm, arm_desc=ARMS[arm], fixture=name, role=spec["role"], kind=spec["kind"],
                rep=rep, model=model, channel="codex-cli",
                artifact="AGENTS.md adapter (INSTRUCTION_ONLY)" if arm == "C" else "none",
                rc=rc, sec=sec, tokens=tokens_of(out), out_chars=len(out),
                verdict="PASS" if gates["correct"] else "FAIL", gates=gates)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A,C")
    ap.add_argument("--fixtures", default=",".join(DEFAULT_FIXTURES))
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--model", default="gpt-5.6-sol")
    ap.add_argument("--codex-home",
                    default=os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex-2")))
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(HERE, "runs", "sol.jsonl"))
    a = ap.parse_args()

    ver = subprocess.run([CODEX, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"channel=codex-cli  version={ver}  model={a.model}  "
          f"home={os.path.basename(a.codex_home)}")
    print("artifact under test: adapters/AGENTS.samewrite.md — an INSTRUCTION FILE, not the "
          "Claude Code skill. Correctness and safety only; token totals are coarse.\n")

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    names = [x.strip() for x in a.fixtures.split(",") if x.strip()]
    jobs = [(arm, n, r) for arm in arms for n in names for r in range(a.repeat)]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    rows, done = [], 0
    with open(a.out, "w", encoding="utf-8") as fh:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = {ex.submit(run_one, arm, n, r, a.model, a.timeout, a.codex_home): (arm, n, r)
                    for arm, n, r in jobs}
            for fut in concurrent.futures.as_completed(futs):
                arm, n, r = futs[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = dict(arm=arm, fixture=n, rep=r, verdict="INFRA_ERROR",
                               infra_reason=f"{type(e).__name__}: {e}", model=a.model)
                rows.append(res)
                fh.write(json.dumps(res) + "\n")
                fh.flush()
                done += 1
                print(f"[{done}/{len(jobs)}] {arm} {n} {res.get('verdict')} "
                      f"tokens={res.get('tokens')}", flush=True)

    print()
    for arm in arms:
        rs = [x for x in rows if x["arm"] == arm and x.get("gates")]
        if not rs:
            continue
        c = sum(1 for x in rs if x["gates"]["correct"])
        s = sum(1 for x in rs if x["gates"]["safety_ok"])
        au = sum(1 for x in rs if x["gates"]["authority_ok"])
        tk = [x["tokens"] for x in rs if x.get("tokens")]
        print(f"  {arm} {ARMS[arm]:<44} correct {c}/{len(rs)}  safety {s}/{len(rs)}  "
              f"authority {au}/{len(rs)}  mean tokens "
              f"{(sum(tk) // len(tk)) if tk else 'unknown'}")
    infra = [x for x in rows if x.get("verdict") == "INFRA_ERROR"]
    print(f"\nwrote {a.out} — {len(rows)} rows, {len(infra)} INFRA_ERROR")
    if infra:
        seen = {}
        for x in infra:
            seen[x.get("infra_reason", "?")] = seen.get(x.get("infra_reason", "?"), 0) + 1
        for why, n in sorted(seen.items(), key=lambda kv: -kv[1]):
            print(f"  {n} x {why}")
    scored = [x for x in rows if x.get("gates")]
    if not scored:
        print("\nSOL_CHANNEL=UNTESTED — every run was an infrastructure failure, so this channel "
              "has NO result. It is not reported as a model outcome and it is not estimated from "
              "the other channel.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
