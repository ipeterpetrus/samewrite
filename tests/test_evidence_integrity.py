#!/usr/bin/env python3
"""Evidence may not describe itself as better than it is.

The 1.3.1 gate refuses to promote a candidate from evidence nobody accepted. An independent
adversarial review then showed five ways evidence could still ARRIVE at that gate looking complete
when it was not, or leave it with the wrong provenance attached:

  H1  a record claimed COMPLETE while its own acquisition counters proved omissions, or while its
      population counts were impossible. The claim was trusted because the schema was new enough.
  H2  a torn JSON line in a transcript was skipped silently, so a sweep that lost evidence still
      reported COMPLETE — no history needed.
  H3  a candidate produced from accepted-PARTIAL evidence was stamped COMPLETE because provenance
      was attached by a finding's POSITION in a list rather than by its source.
  H4  a run whose status said the population was not one world still wrote a candidate file.
  H5  the "was this artifact written before 1.3.1" check was a substring search over the whole
      file: prose satisfied it, an unreadable file was treated as current, and invalid UTF-8
      crashed the process.

The rules these tests freeze:

    A record's quality is the WORST of what it claims and what its own counters prove.
    Quality never improves — not by filtering, not by dedup, not by combination.
    Provenance is attached where a finding is created, from the evidence that created it.
    A status that refuses promotion leaves no candidate file behind.
    An artifact that cannot be parsed is not a trusted artifact.

Expectations here were frozen before the implementation. Standalone: run this file."""
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


def rec(**kw):
    """A schema-2 history record. Counters default to what a clean sweep reports."""
    r = {"schema_version": 2, "samewrite_version": "1.3.1", "record_type": "carry_run",
         "run_id": carry.new_run_id(), "scope_id": "s", "workload_class": "",
         "evidence_quality": "COMPLETE", "unreadable": 0, "oversize": 0, "skipped_by_limit": 0,
         "ts": 1000, "sessions": 40, "turns": 1000, "carry_bytes": 100000, "scanned": 40,
         "runtimes": {}, "models": {}, "shares": {"Bash": 60.0, "Read": 40.0},
         "bpt": {"Bash": 1.0, "Read": 1.0}}
    for k, v in kw.items():
        if v is optimize.__dict__.get("_ABSENT_", object()):
            continue
        r[k] = v
    return r


def without(r, *keys):
    for k in keys:
        r.pop(k, None)
    return r


def moving(n=9, **kw):
    out = []
    for i in range(n):
        d = dict(kw)
        d.setdefault("shares", None)
        r = rec(**{k: v for k, v in d.items() if k != "shares"})
        r["ts"] = 1000 + i * 86400 * 7
        r["shares"] = {"Bash": 20.0 + i * 9, "Read": 80.0 - i * 9}
        r["bpt"] = {"Bash": 1.0, "Read": 1.0}
        r["run_id"] = carry.new_run_id()
        out.append(r)
    return out


def history(name, rows):
    p = os.path.join(WORK, name)
    with open(p, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return p


def profile(name, sessions=20, turns=30, torn=0, interior=False, unreadable=0):
    root = os.path.join(WORK, name, "projects", "-w")
    if os.path.isdir(root):
        return os.path.join(WORK, name)
    os.makedirs(root)
    for i in range(sessions):
        q = os.path.join(root, f"s{i}.jsonl")
        with open(q, "w", encoding="utf-8") as fh:
            for t in range(turns):
                if interior and t == turns // 2:
                    fh.write('{"type": "assistant", "message": {"role": "assi\n')
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
                    {"type": "tool_result", "tool_use_id": f"t{t}", "content": "z" * 200}]}}) + "\n")
            if i < torn:
                fh.write('{"type": "assistant", "message": {"role": "assis')
        if i < unreadable:
            os.chmod(q, 0o000)
    return os.path.join(WORK, name)


def run(h, live=None, accept=False, strict=False, outdir=None, extra=()):
    out = outdir or tempfile.mkdtemp(dir=WORK)
    cmd = [PY, os.path.join(TOOLS, "optimize.py"), "--history", h, "--json",
           "--emit-candidate", out, "--min-turns", "10", "--scan"] + ([live] if live else [])
    if accept:
        cmd.append("--accept-partial")
    if strict:
        cmd.append("--strict-exit")
    cmd += list(extra)
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
    except Exception:
        j = {"status": "<unparsed>", "stderr": r.stderr[-400:]}
    files = [os.path.join(rt, f) for rt, _d, fs in os.walk(out) for f in fs]
    return r.returncode, j, files, out, r


def main():
    global WORK
    WORK = tempfile.mkdtemp(prefix="sw-ei-")
    try:
        return body()
    finally:
        for rt, _d, fs in os.walk(WORK):
            for f in fs:
                try:
                    os.chmod(os.path.join(rt, f), 0o644)
                except OSError:
                    pass
        shutil.rmtree(WORK, ignore_errors=True)


def body():
    # ================================================================ H1
    print("H1 — a record's quality is the worst of what it claims and what its counters prove")
    for label, r, want in [
        ("clean counters, claims COMPLETE", rec(), "COMPLETE"),
        ("unreadable=5 while claiming COMPLETE", rec(unreadable=5), "PARTIAL"),
        ("oversize=2 while claiming COMPLETE", rec(oversize=2), "PARTIAL"),
        ("skipped_by_limit=7 while claiming COMPLETE", rec(skipped_by_limit=7), "PARTIAL"),
        ("malformed_lines=3 while claiming COMPLETE", rec(malformed_lines=3), "PARTIAL"),
        ("sessions=0 with scanned=40 (a sweep that found nothing usable)",
         rec(sessions=0, turns=0, carry_bytes=0), "INVALID"),
        ("sessions=0 with scanned=0 (nothing to sweep)",
         rec(sessions=0, scanned=0, turns=0, carry_bytes=0), "EMPTY"),
        ("a negative counter", rec(unreadable=-1), "INVALID"),
        ("a counter that is not a number", rec(oversize="many"), "INVALID"),
        ("a boolean posing as a counter", rec(skipped_by_limit=True), "INVALID"),
        ("claims COMPLETE but shows no counters at all",
         without(rec(), "unreadable", "oversize", "skipped_by_limit"), "UNKNOWN"),
        ("claims PARTIAL with clean counters (the claim is self-limiting)",
         rec(evidence_quality="PARTIAL"), "PARTIAL"),
        ("claims PARTIAL and the counters agree", rec(evidence_quality="PARTIAL", unreadable=2),
         "PARTIAL"),
        ("claims INVALID with clean counters", rec(evidence_quality="INVALID"), "INVALID"),
        ("schema 1 claiming COMPLETE", rec(schema_version=1), "UNKNOWN"),
    ]:
        check(f"{label} -> {want}", optimize.quality_of(r), want)
    check("quality never improves: worst of COMPLETE and PARTIAL",
          optimize.worst_quality(["COMPLETE", "PARTIAL"]), "PARTIAL")
    _rc, j, files, _o, _r = run(history("h1.jsonl", moving(unreadable=5, oversize=2,
                                                           skipped_by_limit=7)))
    check("a whole history of self-contradicting COMPLETE records cannot promote",
          (j.get("status"), len(files)), ("PARTIAL_EVIDENCE", 0))
    _rc, j, files, _o, _r = run(history("h1b.jsonl", moving(sessions=0, turns=0, carry_bytes=0)))
    check("an impossible population cannot promote", (j.get("status"), len(files)),
          ("INSUFFICIENT_DATA", 0))

    # ================================================================ H2
    print("\nH2 — a sweep that lost a line may not call itself COMPLETE")
    for label, kw, want in [("every line valid", {}, "COMPLETE"),
                            ("one torn final line in one transcript", {"torn": 1}, "PARTIAL"),
                            ("a malformed interior line", {"interior": True}, "PARTIAL"),
                            ("torn lines in every transcript", {"torn": 20}, "PARTIAL")]:
        name = "p_" + label.replace(" ", "_")[:16]
        _rc, j, files, _o, _r = run(history(f"h2_{name}.jsonl", []), live=profile(name, **kw))
        check(f"{label} -> live quality {want}", j.get("evidence_quality"), want)
        if want != "COMPLETE":
            check("   and it cannot promote", len(files), 0)
    # the counter must survive into the history record a later run will read
    hp = os.path.join(WORK, "h2_hist.jsonl")
    subprocess.run([PY, os.path.join(TOOLS, "carry.py"), profile("p_torn_hist", torn=3),
                    "--min-turns", "10", "--history", hp], capture_output=True, text=True)
    rows = [json.loads(l) for l in open(hp, encoding="utf-8") if l.strip()]
    check("the torn count reaches the history record", rows[-1].get("malformed_lines", 0) > 0, True)
    check("and the record says PARTIAL, not COMPLETE", rows[-1]["evidence_quality"], "PARTIAL")

    # ================================================================ H3
    print("\nH3 — provenance comes from a finding's evidence, not from its position in a list")
    import collections as _c
    live_partial = {"sessions": 40, "turns": 2000, "carry": _c.Counter({"Bash": 90, "Read": 10}),
                    "scanned": 40, "short": 0, "quality": "PARTIAL", "unreadable": 1,
                    "oversize": 0, "skipped_by_limit": 0}
    cold = {"cold": 8, "entries": 10, "cold_bytes": 5000, "total_bytes": 6000}
    EMPTY = {"comparable": [], "total": 0, "in_scope": 0, "rejected": {}, "dropped": [],
             "time_order": "ok"}
    out = optimize.analyse(live_partial, EMPTY, None, cold, scope="s", accept_partial=True,
                           effective="PARTIAL")
    ids = {f["id"]: (f["state"], f.get("effective_evidence_quality"),
                     f.get("partial_evidence_accepted")) for f in out}
    for fid, (state, q, acc) in ids.items():
        if state == "CANDIDATE":
            check(f"sampled candidate {fid} carries PARTIAL", q, "PARTIAL")
            check(f"sampled candidate {fid} records the acceptance", acc, True)
    check("the listing candidate is present in this fixture", "listing-prune" in ids, True)
    led = {"writes": 300, "prevented": 1, "rate": 0.3}
    out2 = optimize.analyse(None, EMPTY, led, None, scope="s", accept_partial=False,
                            effective="PARTIAL")
    ledger_findings = [f for f in out2 if f["id"].startswith("noop-guard")]
    check("a ledger finding declares itself as ledger evidence",
          all(f.get("evidence_source") == "ledger" for f in ledger_findings), True)
    check("and is not degraded by sampling it never used",
          all(f.get("effective_evidence_quality") == "COMPLETE" for f in ledger_findings), True)
    check("no finding is left without an evidence source",
          all("evidence_source" in f for f in out + out2), True)

    # ================================================================ H4
    print("\nH4 — a status that refuses promotion leaves no candidate behind")
    shift = moving(n=5, runtimes={"2.1.100": 40}) + \
        [dict(r, runtimes={"2.1.272": 40}) for r in moving(n=4)]
    for i, r in enumerate(shift):
        r["ts"] = 1000 + i * 86400 * 7
        r["shares"] = {"Bash": 20.0 + i * 9, "Read": 80.0 - i * 9}
    cases = [("a clean population", history("h4_ok.jsonl", moving()), {}, "CANDIDATE", True),
             ("a host behaviour shift", history("h4_shift.jsonl", shift), {}, "HOST_BEHAVIOR_SHIFT", False),
             ("partial evidence", history("h4_part.jsonl", moving(evidence_quality="PARTIAL")), {},
              "PARTIAL_EVIDENCE", False),
             ("no evidence", history("h4_none.jsonl", []), {}, "INSUFFICIENT_DATA", False)]
    for label, h, kw, want_status, want_files in cases:
        rc, j, files, _o, _r = run(h, **kw)
        check(f"{label}: status", j.get("status"), want_status)
        check(f"{label}: candidate files {'>0' if want_files else '== 0'}",
              len(files) > 0, want_files)
        check(f"{label}: candidates_written agrees with the filesystem",
              bool(j.get("candidates_written")), want_files)

    # ================================================================ H5
    print("\nH5 — an artifact that cannot be parsed is not a trusted artifact")
    out5 = tempfile.mkdtemp(dir=WORK)
    hp5 = history("h5.jsonl", moving())
    run(hp5, outdir=out5)
    made = [os.path.join(rt, f) for rt, _d, fs in os.walk(out5) for f in fs]
    check("a candidate was written to inspect", len(made), 1)
    if made:
        p = made[0]
        current = open(p, encoding="utf-8").read()
        stripped = "\n".join(l for l in current.splitlines()
                             if not l.startswith(("effective_evidence_quality:",
                                                  "partial_evidence_accepted:")))
        for label, body_text, want_key in [
                ("a current 1.3.1 artifact", current, "candidates_existing"),
                ("a pre-1.3.1 artifact", stripped, "candidates_existing_review_required"),
                ("the marker only in prose", stripped +
                 "\nnote: effective_evidence_quality: is absent here\n",
                 "candidates_existing_review_required"),
                ("an empty marker value", stripped + "\neffective_evidence_quality:\n",
                 "candidates_existing_review_required")]:
            open(p, "w", encoding="utf-8").write(body_text)
            _rc, j, _f, _o, _r = run(hp5, outdir=out5)
            got = [k for k in ("candidates_existing", "candidates_existing_review_required",
                               "candidates_existing_unverifiable") if j.get(k)]
            check(f"{label} -> {want_key}", got, [want_key])
        open(p, "wb").write(b"candidate_id: x\neffective_evidence_quality: \xff\xfe\n")
        rc, j, _f, _o, r = run(hp5, outdir=out5)
        check("invalid UTF-8 does not crash the process", rc, 0)
        check("invalid UTF-8 is reported as unverifiable",
              bool(j.get("candidates_existing_unverifiable")), True)
        open(p, "w", encoding="utf-8").write(current)
        os.chmod(p, 0o000)
        rc, j, _f, _o, _r = run(hp5, outdir=out5)
        os.chmod(p, 0o644)
        check("an unreadable artifact does not crash the process", rc, 0)
        check("an unreadable artifact is reported as unverifiable",
              bool(j.get("candidates_existing_unverifiable")), True)
        check("and is never reported as a trusted existing candidate",
              j.get("candidates_existing"), [])

    # ================================================================ M1
    print("\nM1 — candidates_existing stays machine-readable ids")
    out6 = tempfile.mkdtemp(dir=WORK)
    hp6 = history("m1.jsonl", moving())
    run(hp6, outdir=out6)
    made6 = [os.path.join(rt, f) for rt, _d, fs in os.walk(out6) for f in fs]
    _rc, j6, _f, _o, _r = run(hp6, outdir=out6)
    check("a current artifact appears as a bare id",
          all(" " not in x for x in j6.get("candidates_existing", [])), True)
    check("the id still names a real directory",
          all(os.path.isdir(os.path.join(out6, x)) for x in j6.get("candidates_existing", [])), True)
    if made6:
        t = open(made6[0], encoding="utf-8").read()
        open(made6[0], "w", encoding="utf-8").write("\n".join(
            l for l in t.splitlines()
            if not l.startswith(("effective_evidence_quality:", "partial_evidence_accepted:"))))
    _rc, j6b, _f, _o, _r = run(hp6, outdir=out6)
    check("a pre-1.3.1 artifact does not pollute candidates_existing with prose",
          j6b.get("candidates_existing"), [])
    check("it is listed as a bare id in the review-required field",
          all(" " not in x for x in j6b.get("candidates_existing_review_required", [])), True)
    check("the output schema version is declared", j6b.get("output_schema_version"),
          optimize.OUTPUT_SCHEMA_VERSION)

    # ================================================================ M2
    print("\nM2 — an unusable record may not define the comparison population")
    newest_invalid = rec(evidence_quality="INVALID", workload_class="audit", turns=99,
                         ts=9_999_999_999, sessions=0, carry_bytes=0)
    _rc, j7, f7, _o, _r = run(history("m2.jsonl", moving() + [newest_invalid]))
    check("nine comparable records survive a newest INVALID record",
          j7.get("scope", {}).get("comparable"), 9)
    check("and the run still promotes", (j7.get("status"), len(f7) >= 1), ("CANDIDATE", True))
    newest_empty = rec(evidence_quality="EMPTY", workload_class="other", turns=77,
                       ts=9_999_999_998, sessions=0, scanned=0, carry_bytes=0)
    _rc, j8, f8, _o, _r = run(history("m2b.jsonl", moving() + [newest_empty]))
    check("the same holds for a newest EMPTY record",
          (j8.get("scope", {}).get("comparable"), j8.get("status")), (9, "CANDIDATE"))

    # ================================================================ M3
    print("\nM3 — one definition of a bounded sample")
    pdir = profile("m3", sessions=6, turns=30)
    root = os.path.join(pdir, "projects", "-w")
    paths = sorted(os.path.join(root, f) for f in os.listdir(root))
    for i, q in enumerate(paths):                       # oldest first in discovery order
        os.utime(q, (1_700_000_000 + i * 1000, 1_700_000_000 + i * 1000))
    chosen = carry.bounded_paths(paths, 2)
    check("the bounded selection takes the newest by mtime, not the discovery prefix",
          [os.path.basename(x) for x in chosen],
          [os.path.basename(x) for x in sorted(paths, key=os.path.getmtime, reverse=True)[:2]])
    check("an unbounded selection keeps every path", carry.bounded_paths(paths, 0), paths)
    check("a bound larger than the corpus keeps every path",
          sorted(carry.bounded_paths(paths, 99)), sorted(paths))

    # ================================================================ positive controls
    print("\npositive controls — the gate must still let real evidence through")
    _rc, j, files, _o, _r = run(history("pc_complete.jsonl", moving()))
    check("a complete population crossing the threshold still promotes",
          (j.get("status"), len(files)), ("CANDIDATE", 1))
    _rc, j, files, _o, _r = run(history("pc_partial.jsonl",
                                        moving(evidence_quality="PARTIAL", skipped_by_limit=3)),
                                accept=True)
    check("an accepted partial population still promotes",
          (j.get("status"), len(files)), ("CANDIDATE", 1))
    check("and the acceptance is recorded", j.get("partial_evidence_accepted"), True)
    _rc, j, files, _o, _r = run(history("pc_clean_live.jsonl", []), live=profile("pc_live"))
    check("a clean transcript corpus reads COMPLETE", j.get("evidence_quality"), "COMPLETE")
    _rc, j, files, _o, _r = run(history("pc_unrelated.jsonl",
                                        moving() + moving(evidence_quality="INVALID",
                                                          scope_id="elsewhere")),
                                extra=("--scope-id", "s"))
    check("unrelated invalid evidence does not poison the target population",
          (j.get("status"), len(files) >= 1), ("CANDIDATE", True))

    print(f"\n{P} PASS / {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
