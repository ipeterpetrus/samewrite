#!/usr/bin/env python3
"""A candidate may not be built on evidence nobody agreed to accept.

SW-1303-PARTIAL-EVIDENCE: a history whose records were all written by bounded sweeps
(`carry.py --max-files N`) produced a CANDIDATE with exit 0, identically to a history swept in
full, and a COMPLETE live scan masked it. The quality gate read the live scan only; the quality
carried by the history records never entered the decision.

The rule these tests freeze:

    A finding may become a CANDIDATE only when the WORST quality among the evidence ACTUALLY
    ELIGIBLE to support it is COMPLETE — or is PARTIAL and the caller passed --accept-partial.

"Actually eligible" is the load-bearing half. `comparable()` already decides which history records
may support a finding: same scope, same workload class, compatible corpus size, quality not
INVALID/EMPTY. A partial record in another scope, under another workload class, or dropped as
non-comparable is not evidence for this finding and must not block it. Without that half the fix
would be a fail-closed switch that blocks everything, which is not the same thing as correct.

The matrix below is frozen: it was written, with its expected outcomes, before the implementation.

Standalone: run this file."""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import carry, optimize  # noqa: E402

PY = sys.executable
P = F = 0
WORK = None


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


# ---------------------------------------------------------------- fixtures
def rec(ts, shares, quality="COMPLETE", scope="s", workload="", turns=1000, drop_quality=False,
        schema=None):
    r = {"schema_version": schema if schema is not None else carry.HISTORY_SCHEMA,
         "samewrite_version": "1.3.1", "record_type": "carry_run",
         "run_id": carry.new_run_id(), "scope_id": scope, "workload_class": workload,
         "evidence_quality": quality, "unreadable": 0, "oversize": 0, "skipped_by_limit": 0,
         "ts": ts, "sessions": 40, "turns": turns, "carry_bytes": 100000, "scanned": 40,
         "runtimes": {}, "models": {}, "shares": shares, "bpt": {k: 1.0 for k in shares}}
    if drop_quality:
        del r["evidence_quality"]
    return r


def moving(n=9, quality="COMPLETE", scope="s", workload="", qualities=None, drop_quality=False,
           schema=None):
    """A history that crosses the trend threshold: Bash climbs 9 pp per record."""
    out = []
    for i in range(n):
        q = qualities[i] if qualities else quality
        out.append(rec(1000 + i * 86400 * 7, {"Bash": 20.0 + i * 9, "Read": 80.0 - i * 9},
                       q, scope, workload, drop_quality=drop_quality, schema=schema))
    return out


def history(name, records):
    p = os.path.join(WORK, name)
    with open(p, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    return p


def profile(name, sessions=30, turns=30, tool_bytes=200):
    """A transcript corpus big enough to clear the concentration floor when swept in full."""
    root = os.path.join(WORK, name, "projects", "-w")
    if os.path.isdir(root):
        return os.path.join(WORK, name)
    os.makedirs(root)
    for i in range(sessions):
        with open(os.path.join(root, f"s{i}.jsonl"), "w", encoding="utf-8") as fh:
            for t in range(turns):
                fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                    {"type": "text", "text": "q"}]}}) + "\n")
                fh.write(json.dumps({"type": "assistant", "version": "2.1.272",
                                     "message": {"role": "assistant", "model": "claude-opus-5",
                                                 "usage": {"input_tokens": 1000, "output_tokens": 200,
                                                           "cache_read_input_tokens": 5000,
                                                           "cache_creation_input_tokens": 0},
                                                 "content": [{"type": "tool_use", "id": f"t{t}",
                                                              "name": "Bash",
                                                              "input": {"command": "ls"}}]}}) + "\n")
                fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": f"t{t}",
                     "content": "z" * tool_bytes}]}}) + "\n")
    return os.path.join(WORK, name)


def run(hist_path, live=None, max_files=None, accept_partial=False, scope=None, strict=False):
    """-> (exit code, parsed json, number of candidate files written)."""
    out = tempfile.mkdtemp(dir=WORK)
    cmd = [PY, os.path.join(TOOLS, "optimize.py"), "--history", hist_path, "--json",
           "--emit-candidate", out, "--min-turns", "10"]
    cmd += ["--scan"] + ([live] if live else [])
    if max_files:
        cmd += ["--max-files", str(max_files)]
    if accept_partial:
        cmd += ["--accept-partial"]
    if scope:
        cmd += ["--scope-id", scope]
    if strict:
        cmd += ["--strict-exit"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
    except Exception:
        j = {"status": "<unparsed>", "_stderr": r.stderr[-400:]}
    n = sum(len(files) for _r, _d, files in os.walk(out))
    return r.returncode, j, n


# ---------------------------------------------------------------- the frozen matrix
# case, description, kwargs, expected status, expected candidate files
MATRIX = [
    ("A", "COMPLETE history only",
     dict(records=moving()), "CANDIDATE", 1),
    ("B", "PARTIAL history only, no acceptance",
     dict(records=moving(quality="PARTIAL")), "PARTIAL_EVIDENCE", 0),
    ("C", "COMPLETE live only, no history",
     dict(records=[], live=True), "CANDIDATE", 1),
    ("D", "PARTIAL live only (bounded sweep above the floor)",
     dict(records=[], live=True, max_files=22), "PARTIAL_EVIDENCE", 0),
    ("E", "PARTIAL history + COMPLETE live — live must not mask it",
     dict(records=moving(quality="PARTIAL"), live=True), "PARTIAL_EVIDENCE", 0),
    ("F", "COMPLETE history + PARTIAL live",
     dict(records=moving(), live=True, max_files=22), "PARTIAL_EVIDENCE", 0),
    ("G", "mixed comparable history: one PARTIAL among COMPLETE",
     dict(records=moving(qualities=["COMPLETE"] * 2 + ["PARTIAL"] + ["COMPLETE"] * 6)),
     "PARTIAL_EVIDENCE", 0),
    ("H", "PARTIAL record in an UNRELATED SCOPE must not block",
     dict(records=moving() + moving(quality="PARTIAL", scope="other"), scope="s"),
     "CANDIDATE", 1),
    ("I", "PARTIAL record in an UNRELATED WORKLOAD CLASS must not block",
     dict(records=moving() + moving(quality="PARTIAL", workload="audit")), "CANDIDATE", 1),
    ("J", "an INVALID record that comparable() drops must not block",
     dict(records=moving() + [rec(9999999999, {"Bash": 50.0, "Read": 50.0}, "INVALID")]),
     "CANDIDATE", 1),
    ("K", "INVALID live evidence is never promotion-grade",
     dict(records=moving(), live=True, invalid_live=True), "PARTIAL_EVIDENCE", 0),
    ("L", "legacy records with no evidence_quality are UNKNOWN, not COMPLETE",
     dict(records=moving(drop_quality=True, schema=1)), "PARTIAL_EVIDENCE", 0),
    ("M", "accepted PARTIAL bounded evidence still produces a candidate",
     dict(records=moving(quality="PARTIAL"), accept_partial=True), "CANDIDATE", 1),
    ("N", "--accept-partial does NOT authorise INVALID",
     dict(records=moving(), live=True, invalid_live=True, accept_partial=True),
     "PARTIAL_EVIDENCE", 0),
    ("O", "no evidence at all",
     dict(records=[]), "INSUFFICIENT_DATA", 0),
]


def main():
    global WORK
    WORK = tempfile.mkdtemp(prefix="sw-eq-")
    try:
        return body()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)


def body():
    # ------------------------------------------------------------ the lattice, as a unit
    print("evidence-quality lattice")
    check("a missing evidence_quality is UNKNOWN, never COMPLETE",
          optimize.quality_of({"schema_version": 1}), "UNKNOWN")
    check("an unrecognised evidence_quality is UNKNOWN",
          optimize.quality_of({"evidence_quality": "PROBABLY_FINE"}), "UNKNOWN")
    check("a recognised value passes through",
          optimize.quality_of({"evidence_quality": "PARTIAL"}), "PARTIAL")
    check("worst-of picks the worst, not the most common",
          optimize.worst_quality(["COMPLETE", "COMPLETE", "PARTIAL", "COMPLETE"]), "PARTIAL")
    check("worst-of over nothing is COMPLETE (a finding with no sampled evidence is not degraded)",
          optimize.worst_quality([]), "COMPLETE")
    check("INVALID outranks PARTIAL", optimize.worst_quality(["PARTIAL", "INVALID"]), "INVALID")
    check("UNKNOWN outranks PARTIAL", optimize.worst_quality(["PARTIAL", "UNKNOWN"]), "UNKNOWN")
    for q, ap, want in (("COMPLETE", False, True), ("COMPLETE", True, True),
                        ("PARTIAL", False, False), ("PARTIAL", True, True),
                        ("UNKNOWN", False, False), ("UNKNOWN", True, False),
                        ("INVALID", False, False), ("INVALID", True, False),
                        ("EMPTY", False, False), ("EMPTY", True, False)):
        check(f"emittable({q}, accept_partial={ap})", optimize.emittable(q, ap), want)

    # ------------------------------------------------------------ the frozen matrix
    print("\nfrozen regression matrix")
    live_dir = profile("p")
    for case, desc, kw, want_status, want_files in MATRIX:
        recs = kw.get("records")
        hp = history(f"h_{case}.jsonl", recs)
        live = live_dir if kw.get("live") else None
        if kw.get("invalid_live"):
            # an unreadable transcript directory: the sweep runs but its evidence is not a population
            bad = os.path.join(WORK, f"bad_{case}", "projects", "-w")
            os.makedirs(bad, exist_ok=True)
            with open(os.path.join(bad, "s0.jsonl"), "w") as fh:
                fh.write("{not json\n")
            live = os.path.join(WORK, f"bad_{case}")
        rc, j, n = run(hp, live=live, max_files=kw.get("max_files"),
                       accept_partial=kw.get("accept_partial", False), scope=kw.get("scope"))
        eq = j.get("effective_evidence_quality")
        check(f"{case}  {desc}  -> status", j.get("status"), want_status)
        check(f"{case}  {desc}  -> candidate files", n, want_files)
        print(f"        effective_evidence_quality={eq!r} "
              f"partial_evidence_accepted={j.get('partial_evidence_accepted')!r} exit={rc}")

    # ------------------------------------------------------------ provenance and contract
    print("\nprovenance, JSON contract and exit contract")
    hp = history("h_prov.jsonl", moving(quality="PARTIAL"))
    out = tempfile.mkdtemp(dir=WORK)
    r = subprocess.run([PY, os.path.join(TOOLS, "optimize.py"), "--history", hp, "--scan",
                        "--json", "--accept-partial", "--emit-candidate", out, "--min-turns", "10"],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    check("accepted PARTIAL reports its effective quality in JSON",
          j.get("effective_evidence_quality"), "PARTIAL")
    check("accepted PARTIAL records the acceptance in JSON",
          j.get("partial_evidence_accepted"), True)
    check("the JSON schema version is still declared", j.get("output_schema_version"),
          optimize.OUTPUT_SCHEMA_VERSION)
    cand = [os.path.join(rt, f) for rt, _d, fs in os.walk(out) for f in fs]
    check("a candidate was written", len(cand), 1)
    if cand:
        text = open(cand[0], encoding="utf-8").read()
        check("the candidate file states its effective evidence quality",
              "effective_evidence_quality: PARTIAL" in text, True)
        check("the candidate file states that partial evidence was accepted",
              "partial_evidence_accepted: true" in text, True)
        check("the candidate still carries scope", "scope_id:" in text, True)
        check("the candidate still carries the threshold schema version",
              "threshold_schema_version:" in text, True)
        for leak in ("/home/", "ADVCANARY", "tool_result"):
            check(f"the candidate leaks no {leak!r}", leak in text, False)
    # per-finding quality, so a consumer need not re-derive it
    check("every finding carries its own effective quality",
          all("effective_evidence_quality" in f for f in j.get("findings", [])), True)

    # human output must say WHY, not just refuse
    hp2 = history("h_why.jsonl", moving(quality="PARTIAL"))
    r2 = subprocess.run([PY, os.path.join(TOOLS, "optimize.py"), "--history", hp2, "--scan",
                         "--min-turns", "10"], capture_output=True, text=True)
    check("the human report names the evidence quality that blocked promotion",
          "PARTIAL" in r2.stdout, True)
    check("the human report does not silently print nothing", len(r2.stdout.strip()) > 0, True)

    # exit contract, both modes
    rc_norm, j_norm, _ = run(hp2)
    rc_strict, j_strict, _ = run(hp2, strict=True)
    check("normal mode keeps exit 0 (unchanged public behaviour)", rc_norm, 0)
    check("normal mode still reports the blocking status in JSON", j_norm.get("status"),
          "PARTIAL_EVIDENCE")
    check("--strict-exit returns the documented PARTIAL_EVIDENCE code", rc_strict,
          optimize.STATUS["PARTIAL_EVIDENCE"])
    rc_ok, _j, _n = run(history("h_ok.jsonl", moving()), strict=True)
    check("--strict-exit still returns the CANDIDATE code on complete evidence", rc_ok,
          optimize.STATUS["CANDIDATE"])

    # ------------------------------------------------------------ the real AI-VOS path
    # Not a synthetic history: drive the actual commands a 24x7 operator runs. Bounded sweeps are
    # how a large profile is kept affordable, and they are exactly what produced SW-1303.
    print("\nthe AI-VOS-shaped path: repeated bounded sweeps, then an analysis")
    live_dir2 = profile("p2", sessions=30, turns=30)
    hb = os.path.join(WORK, "h_bounded.jsonl")
    for i in range(6):
        r = subprocess.run([PY, os.path.join(TOOLS, "carry.py"), live_dir2, "--min-turns", "10",
                            "--max-files", "22", "--history", hb, "--scope-id", "aivos"],
                           capture_output=True, text=True)
    rows = [json.loads(l) for l in open(hb, encoding="utf-8") if l.strip()]
    check("six bounded sweeps wrote six records", len(rows), 6)
    check("every one is marked PARTIAL by the observer itself",
          sorted({r["evidence_quality"] for r in rows}), ["PARTIAL"])
    check("and each records how much it skipped",
          all(r.get("skipped_by_limit", 0) > 0 for r in rows), True)

    out = tempfile.mkdtemp(dir=WORK)
    r = subprocess.run([PY, os.path.join(TOOLS, "optimize.py"), "--history", hb, "--scan",
                        "--scope-id", "aivos", "--json", "--emit-candidate", out],
                       capture_output=True, text=True)
    j = json.loads(r.stdout)
    n = sum(len(f) for _r, _d, f in os.walk(out))
    check("without --accept-partial the bounded history yields PARTIAL_EVIDENCE",
          j.get("status"), "PARTIAL_EVIDENCE")
    check("and writes no candidate file", n, 0)
    check("effective quality is reported as PARTIAL", j.get("effective_evidence_quality"), "PARTIAL")

    out2 = tempfile.mkdtemp(dir=WORK)
    r2 = subprocess.run([PY, os.path.join(TOOLS, "optimize.py"), "--history", hb, "--scan",
                         "--scope-id", "aivos", "--json", "--accept-partial",
                         "--emit-candidate", out2], capture_output=True, text=True)
    j2 = json.loads(r2.stdout)
    check("with explicit acceptance the bounded population is analysable again",
          j2.get("status") in ("CANDIDATE", "NO_ACTION", "INSUFFICIENT_DATA"), True)
    check("and the acceptance is recorded, not implied",
          j2.get("partial_evidence_accepted"), True)
    print(f"        accepted-partial status: {j2.get('status')}")

    # ------------------------------------------------------------ privacy over the new fields
    # The fix added text to the candidate file and to the JSON. New output is new leak surface.
    print("\nprivacy: canaries through the new provenance surfaces")
    CANARY = {"scope": "CANARYSCOPE_7f3a1b", "workload": "CANARYWORK_2d9c4e"}
    recs = moving(quality="PARTIAL", scope=CANARY["scope"], workload=CANARY["workload"])
    hp3 = history("h_canary.jsonl", recs)
    out3 = tempfile.mkdtemp(dir=WORK)
    r3 = subprocess.run([PY, os.path.join(TOOLS, "optimize.py"), "--history", hp3, "--scan",
                         "--accept-partial", "--emit-candidate", out3, "--json"],
                        capture_output=True, text=True)
    r4 = subprocess.run([PY, os.path.join(TOOLS, "optimize.py"), "--history", hp3, "--scan",
                         "--accept-partial"], capture_output=True, text=True)
    blob = r3.stdout + r3.stderr + r4.stdout + r4.stderr
    for rt, _d, fs in os.walk(out3):
        for f in fs:
            blob += open(os.path.join(rt, f), encoding="utf-8", errors="replace").read()
    # scope and workload are operator-chosen labels and ARE meant to travel: they are the thing
    # that keeps two agents' populations apart. What must never travel is content.
    for forbidden in ("tool_result", "ADVCANARY", os.path.expanduser("~") + "/.claude",
                      "prompt:", "SKILL.md"):
        check(f"no {forbidden!r} in any optimizer output surface", forbidden in blob, False)
    check("the scope label the operator chose does travel (it is the isolation key)",
          CANARY["scope"] in blob, True)
    src_opt = open(os.path.join(TOOLS, "optimize.py"), encoding="utf-8").read()
    import re as _re
    for label, pat in (("network", r"\bimport\s+(socket|urllib|requests|http\.client)\b"),
                       ("subprocess", r"\bimport\s+subprocess\b|\bsubprocess\."),
                       ("model call", r"\banthropic\b|\bopenai\b")):
        check(f"optimizer still has no {label} path", _re.findall(pat, src_opt), [])

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
