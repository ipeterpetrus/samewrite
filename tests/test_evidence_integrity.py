#!/usr/bin/env python3
"""v1.4.2 — one case per row of docs/V142_COUNTEREXAMPLES.md.

The legacy optimizer promoted findings from evidence it had never checked: a history built from
bounded sweeps, a record claiming a completeness its own numbers contradict, a population anchored
on the one record that was thrown away, a sweep that lost records to torn JSON, and a status that
refused promotion while still writing the candidate file to disk.

Every case below is a counterexample first and a regression second: it was RED on 77e3677, and the
matrix that says what it must do was frozen before the repair existed.

Standalone: run this file."""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPT = os.path.join(ROOT, "tools", "optimize.py")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import carry                                                            # noqa: E402
import optimize                                                         # noqa: E402

P = F = 0
TS0 = 1_750_000_000


def check(label, got, want):
    global P, F
    if got == want:
        P += 1
        print(f"  PASS  {label}")
    else:
        F += 1
        print(f"  FAIL  {label}: got {got!r}, want {want!r}")


def rec(i, share, quality="COMPLETE", schema=2, counters=True, sessions=40, turns=1000,
        carry_bytes=10 ** 7, scanned=100, scope="default", workload="code", runtime="2.1.270",
        unreadable=0, oversize=0, skipped=0):
    """One legacy history record, shaped like the one carry.history() wrote in 1.2/1.3.

    `counters=False` is the record a hand-edited file or a back-filled migration produces: it
    claims a quality it never acquired the facts for."""
    r = {"schema_version": schema, "record_type": "carry_run", "run_id": f"r{scope}{i}",
         "scope_id": scope, "workload_class": workload, "ts": TS0 + i * 604800,
         "sessions": sessions, "turns": turns, "carry_bytes": carry_bytes, "scanned": scanned,
         "runtimes": {runtime: 40}, "models": {"m1": 40},
         "shares": {"Bash": round(share, 4), "Read": round(100.0 - share, 4)},
         "bpt": {"Bash": 1.0, "Read": 1.0}}
    if schema >= 2:
        r["evidence_quality"] = quality
        if counters:
            r.update(unreadable=unreadable, oversize=oversize, skipped_by_limit=skipped)
    return r


def write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return path


def run(rows, extra=(), scan=(), lock=False):
    """Run the optimizer as the scheduler runs it -> (exit code, parsed --json, files on disk)."""
    d = tempfile.mkdtemp(prefix="sw-142-")
    hist = write(os.path.join(d, "history.jsonl"), rows)
    out = os.path.join(d, "cand")
    if lock:
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, ".optimize.lock"), "w").write("1")
    argv = [sys.executable, OPT, "--history", hist, "--ledger", os.path.join(d, "none.jsonl"),
            "--emit-candidate", out, "--json", "--strict-exit", "--scan"] + list(scan) + list(extra)
    p = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    try:
        j = json.loads(p.stdout)
    except Exception:
        raise SystemExit(f"optimizer produced no JSON (rc={p.returncode}):\n{p.stdout}\n{p.stderr}")
    files = [f for _b, _d, fs in os.walk(out) for f in fs if f != ".optimize.lock"]
    return p.returncode, j, len(files)


def case(label, rows, status, code, files, comparable=None, extra=(), scan=(), lock=False,
         history_quality=None):
    rc, j, n = run(rows, extra=extra, scan=scan, lock=lock)
    check(f"{label}: status", j["status"], status)
    check(f"{label}: strict exit", rc, code)
    check(f"{label}: candidate files on disk", n, files)
    if comparable is not None:
        check(f"{label}: comparable", j["history"]["comparable"], comparable)
    if history_quality is not None:
        check(f"{label}: history quality", j["history"].get("quality"), history_quality)
    return j


def transcript(path, turns=80, listing=False, torn=False):
    """A minimal Claude-Code-shaped transcript: enough turns to be a session, optionally one
    skill listing attachment, optionally one torn JSON record."""
    rows = []
    if listing:
        rows.append(json.dumps({"type": "user", "attachment": {
            "type": "skill_listing",
            "content": "- alpha: does a thing that is described at some length\n"
                       "- beta: does another thing, also described at some length\n"}}))
    for t in range(turns):
        rows.append(json.dumps({"type": "assistant", "message": {
            "id": f"msg_{t}", "usage": {"input_tokens": 10, "output_tokens": 7},
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}}]}}))
        rows.append(json.dumps({"type": "user", "message": {
            "content": [{"type": "tool_result", "content": "o" * 400}]}}))
    if torn:
        rows[len(rows) // 2] = '{"type": "assistant", "message": {"usage": {"out'
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    return path


EMPTY_HIST = {"comparable": [], "total": 0, "in_scope": 0, "rejected": {}, "dropped": [],
              "time_order": "ok"}


def main():
    d = tempfile.mkdtemp(prefix="sw-142-fx-")
    good_rows = [rec(i, 30.0 + 3.0 * i) for i in range(6)]

    # ---------------------------------------------------------------- the law itself
    print("\nlegacy evidence-quality law")
    check("worst wins, not the majority",
          optimize.worst_quality(["COMPLETE", "COMPLETE", "PARTIAL", "COMPLETE"]), "PARTIAL")
    check("no evidence is not bad evidence", optimize.worst_quality([]), "COMPLETE")
    check("a schema older than the field cannot claim the field",
          optimize.record_quality(rec(0, 40.0, schema=1, counters=False)), "UNKNOWN")
    check("schema 2 without the counters its writer always wrote",
          optimize.record_quality(rec(0, 40.0, counters=False)), "UNKNOWN")
    check("counters present and zero: COMPLETE is attested",
          optimize.record_quality(rec(0, 40.0)), "COMPLETE")
    check("a chosen bound is PARTIAL",
          optimize.record_quality(rec(0, 40.0, skipped=5)), "PARTIAL")
    check("a loss is DEGRADED, not a chosen bound",
          optimize.record_quality(rec(0, 40.0, unreadable=3)), "DEGRADED")
    check("the claim cannot be better than the counters",
          optimize.record_quality(rec(0, 40.0, quality="COMPLETE", oversize=1)), "DEGRADED")
    check("the counters cannot be better than the claim",
          optimize.record_quality(rec(0, 40.0, quality="PARTIAL")), "PARTIAL")
    check("looked and found nothing usable: INVALID",
          optimize.record_quality(rec(0, 40.0, sessions=0, scanned=100)), "INVALID")
    check("had nothing to look at: EMPTY",
          optimize.record_quality(rec(0, 40.0, sessions=0, scanned=0)), "EMPTY")
    check("sessions without turns is not a sweep that happened",
          optimize.record_quality(rec(0, 40.0, turns=0)), "INVALID")
    check("sessions without carry is not a sweep that happened",
          optimize.record_quality(rec(0, 40.0, carry_bytes=0)), "INVALID")
    check("a count that is not a count",
          optimize.record_quality(rec(0, 40.0, unreadable=-1)), "INVALID")
    check("a boolean is not a count",
          optimize.record_quality(rec(0, 40.0, oversize=True)), "INVALID")
    check("--accept-partial accepts the bound it is named for",
          optimize.may_promote("PARTIAL", True), True)
    check("--accept-partial does not accept a loss",
          optimize.may_promote("DEGRADED", True), False)
    check("--accept-partial does not accept what cannot be verified",
          optimize.may_promote("UNKNOWN", True), False)
    check("--accept-partial does not accept an invalid record",
          optimize.may_promote("INVALID", True), False)
    check("COMPLETE needs no flag", optimize.may_promote("COMPLETE", False), True)
    check("PARTIAL without the flag stays refused", optimize.may_promote("PARTIAL", False), False)

    # ---------------------------------------------------------------- R142_01 / R142_01P
    print("\nR142_01 - a history built from bounded sweeps is not a population")
    partial = [rec(i, 30.0 + 3.0 * i, quality="PARTIAL", skipped=5) for i in range(6)]
    case("R142_01", partial, "PARTIAL_EVIDENCE", 40, 0, comparable=6, history_quality="PARTIAL")
    case("R142_01P (--accept-partial)", partial, "CANDIDATE", 10, 1, comparable=6,
         extra=["--accept-partial"], history_quality="PARTIAL")

    # ---------------------------------------------------------------- R142_02
    print("\nR142_02 - the anchor comes from evidence that survives its own filter")
    stranding = [rec(i, 30.0 + 3.0 * i) for i in range(6)]
    stranding.append(rec(9, 55.0, quality="INVALID", sessions=0, turns=100000, carry_bytes=0))
    case("R142_02", stranding, "CANDIDATE", 10, 1, comparable=6, history_quality="COMPLETE")

    # ---------------------------------------------------------------- R142_03
    print("\nR142_03 - a status that refuses promotion writes nothing")
    shifted = ([rec(i, 30.0 + 4.0 * i, runtime="2.1.270") for i in range(3)]
               + [rec(i, 30.0 + 4.0 * i, runtime="2.1.290") for i in range(3, 6)])
    case("R142_03", shifted, "HOST_BEHAVIOR_SHIFT", 30, 0, comparable=6)

    # ---------------------------------------------------------------- R142_04
    print("\nR142_04 - a record cannot claim a completeness its own numbers contradict")
    impossible = [rec(i, 30.0 + 3.0 * i, sessions=0, turns=0, carry_bytes=0) for i in range(6)]
    case("R142_04", impossible, "PARTIAL_EVIDENCE", 40, 0, comparable=0)

    # ---------------------------------------------------------------- R142_05
    print("\nR142_05 - a sweep that lost records to torn JSON is not COMPLETE")
    clean = transcript(os.path.join(d, "clean.jsonl"))
    torn = transcript(os.path.join(d, "torn.jsonl"), torn=True)
    a_clean, a_torn = carry.accumulate([clean], min_turns=1), carry.accumulate([torn], min_turns=1)
    check("control: a clean sweep is still COMPLETE", a_clean["quality"], "COMPLETE")
    check("the torn record is counted", a_torn["malformed"], 1)
    check("and the sweep is no longer COMPLETE", a_torn["quality"] != "COMPLETE", True)
    check("the optimizer reads it as a loss, not a bound",
          optimize.sweep_quality(a_torn), "DEGRADED")
    check("control: the clean sweep reads COMPLETE", optimize.sweep_quality(a_clean), "COMPLETE")
    check("a loss is not rescued by --accept-partial",
          optimize.may_promote(optimize.sweep_quality(a_torn), True), False)
    case("R142_05 (live, torn)", [], "PARTIAL_EVIDENCE", 40, 0, scan=[torn, "--min-turns", "1"])
    case("R142_05 (live, torn, --accept-partial)", [], "PARTIAL_EVIDENCE", 40, 0,
         scan=[torn, "--min-turns", "1"], extra=["--accept-partial"])

    # ---------------------------------------------------------------- R142_06
    print("\nR142_06 - one definition of a bounded sample")
    paths = []
    for n, name in enumerate(("a.jsonl", "b.jsonl", "c.jsonl")):
        p = transcript(os.path.join(d, name), turns=60, listing=(name == "a.jsonl"))
        os.utime(p, (TS0 + n * 1000, TS0 + n * 1000))         # a oldest, c newest
        paths.append(p)
    check("the bound is the newest N",
          [os.path.basename(p) for p in carry.bounded_paths(paths, 1)], ["c.jsonl"])
    check("and it does not depend on discovery order",
          carry.bounded_paths(list(reversed(paths)), 1), carry.bounded_paths(paths, 1))
    check("an unbounded sweep keeps every source", carry.bounded_paths(paths, 0), paths)
    _rc, j, _n = run([], scan=paths + ["--max-files", "1", "--min-turns", "1"])
    check("the listing scan reads the sweep's sample, not a discovery-order slice",
          j["listing"], None)
    _rc, j2, _n = run([], scan=paths + ["--min-turns", "1"])
    check("control: unbounded, the listing in the oldest transcript IS read",
          bool(j2["listing"]), True)

    # ---------------------------------------------------------------- the bound itself
    print("\nthe bound a caller asked for is not a loss (and is still not COMPLETE)")
    bounded = carry.accumulate(paths, min_turns=1, max_files=1)
    check("a bounded sweep records what it skipped", bounded["skipped_by_limit"], 2)
    check("the producer labels it PARTIAL", bounded["quality"], "PARTIAL")
    check("the optimizer reads a bound, not a loss", optimize.sweep_quality(bounded), "PARTIAL")
    check("refused without the flag",
          optimize.may_promote(optimize.sweep_quality(bounded), False), False)
    check("adopted with it", optimize.may_promote(optimize.sweep_quality(bounded), True), True)

    # ---------------------------------------------------------------- U1
    print("\nU1 - a generation that never had the field cannot have defaulted to COMPLETE")
    old = [rec(i, 30.0 + 3.0 * i, schema=1, counters=False) for i in range(6)]
    case("U1", old, "PARTIAL_EVIDENCE", 40, 0, comparable=6, history_quality="UNKNOWN")
    case("U1 (--accept-partial does not rescue it)", old, "PARTIAL_EVIDENCE", 40, 0,
         extra=["--accept-partial"])

    # ---------------------------------------------------------------- a retry cannot launder
    print("\nR142_07 - a retry cannot upgrade what its own run_id saw")
    dup = [rec(i, 30.0 + 3.0 * i) for i in range(5)]
    dup.append(rec(5, 45.0))
    dup[-1]["run_id"] = "dup"
    worse = rec(5, 45.0, quality="PARTIAL", skipped=7)
    worse["run_id"] = "dup"
    dup.append(worse)
    hist_path = write(os.path.join(d, "dup.jsonl"), dup)
    recs, rejected, _lines = optimize.load_history(hist_path)
    check("the retry is dropped as an observation", len(recs), 6)
    check("and counted", rejected["duplicate run_id (retry)"], 1)
    keep, _dropped = optimize.comparable(recs)
    check("but its quality travels with the record that survived",
          optimize.history_quality(keep), "PARTIAL")
    case("R142_07", dup, "PARTIAL_EVIDENCE", 40, 0, history_quality="PARTIAL")
    case("R142_07 (--accept-partial adopts the bound)", dup, "CANDIDATE", 10, 1,
         extra=["--accept-partial"])
    check("a schema_version this reader cannot name is not a newer one",
          optimize.record_quality(dict(rec(0, 40.0), schema_version="2")), "UNKNOWN")
    check("nor is a float one",
          optimize.record_quality(dict(rec(0, 40.0), schema_version=2.0)), "UNKNOWN")

    # ------------------------------------------------- round-1 cross-family review findings
    print("\nR142_08 - what a record must SHOW before its zeroes mean anything")
    no_corpus = {"schema_version": 2, "record_type": "carry_run", "ts": TS0,
                 "evidence_quality": "COMPLETE", "unreadable": 0, "oversize": 0,
                 "skipped_by_limit": 0, "shares": {"Bash": 60.0, "Read": 40.0},
                 "bpt": {"Bash": 1.0, "Read": 1.0}}
    check("zero counters do not say a sweep happened",
          optimize.record_quality(no_corpus), "UNKNOWN")
    for missing in ("sessions", "turns", "carry_bytes"):
        partial_rec = {k: v for k, v in rec(0, 40.0).items() if k != missing}
        check(f"a record without {missing} cannot attest completeness",
              optimize.record_quality(partial_rec), "UNKNOWN")

    print("\nR142_09 - one undateable source does not collapse the bound")
    undated = []
    for n, name in enumerate(("x.jsonl", "y.jsonl", "z.jsonl")):
        q = transcript(os.path.join(d, name), turns=5)
        os.utime(q, (TS0 + n * 1000, TS0 + n * 1000))            # z newest
        undated.append(q)
    os.remove(undated[2])                                      # ...and now undateable
    picked = [os.path.basename(q) for q in carry.bounded_paths(undated, 2)]
    check("the datable sources still order by mtime", picked, ["y.jsonl", "x.jsonl"])
    check("and discovery order still does not matter",
          carry.bounded_paths(list(reversed(undated)), 2), carry.bounded_paths(undated, 2))

    print("\nR142_10 - counters that cannot describe one sweep")
    check("more sessions than transcripts scanned",
          optimize.record_quality(rec(0, 40.0, sessions=40, scanned=1)), "INVALID")
    check("sessions out of a sweep that scanned nothing",
          optimize.record_quality(rec(0, 40.0, sessions=40, scanned=0)), "INVALID")
    check("...and the bound flag does not rescue that either",
          optimize.may_promote(optimize.record_quality(
              rec(0, 40.0, quality="PARTIAL", sessions=40, scanned=0, skipped=5)), True), False)
    check("control: sessions within what was scanned",
          optimize.record_quality(rec(0, 40.0, sessions=40, scanned=40)), "COMPLETE")
    case("R142_10", [rec(i, 30.0 + 3.0 * i, sessions=40, scanned=1) for i in range(6)],
         "PARTIAL_EVIDENCE", 40, 0, comparable=0)

    print("\nR142_11 - a torn line in the history file is lost evidence, not a footnote")
    torn_hist = [json.dumps(r) for r in good_rows] + ['{"torn":']
    j = case("R142_11", torn_hist, "PARTIAL_EVIDENCE", 40, 0, history_quality="DEGRADED")
    check("the torn line is still counted", j["history"]["rejected"].get("unparseable line"), 1)
    case("R142_11 (--accept-partial does not adopt a loss)", torn_hist,
         "PARTIAL_EVIDENCE", 40, 0, extra=["--accept-partial"])
    envelope_line = json.dumps({"envelope": {"schema_version": 4, "run_id": "x"},
                                "payload": {}, "certificate": {}})
    foreign = json.dumps({"note": "another tool's line in a shared file"})
    case("R142_11 control: a foreign line that parses is counted, not called damage",
         [json.dumps(r) for r in good_rows] + [foreign], "CANDIDATE", 10, 1,
         history_quality="COMPLETE")
    case("R142_11 control: a refusal by design is not damage",
         [json.dumps(r) for r in good_rows] + [envelope_line], "CANDIDATE", 10, 1,
         history_quality="COMPLETE")

    print("\nR142_12 - a ledger that lost a line is not a field sample")
    ledger_dir = tempfile.mkdtemp(dir=d)
    clean_ledger = os.path.join(ledger_dir, "clean.jsonl")
    with open(clean_ledger, "w", encoding="utf-8") as fh:
        fh.write("\n".join('{"event": "checked"}' for _ in range(100)) + "\n")
    torn_ledger = os.path.join(ledger_dir, "torn.jsonl")
    with open(torn_ledger, "w", encoding="utf-8") as fh:
        fh.write("\n".join('{"event": "checked"}' for _ in range(100)) + "\n" + '{"event":' + "\n")
    clean = optimize.load_ledger(clean_ledger)
    lost = optimize.load_ledger(torn_ledger)
    check("control: a clean sample retires the guard",
          [f["state"] for f in optimize.analyse(None, dict(EMPTY_HIST), clean, None)], ["CANDIDATE"])
    check("a sample that lost a line only observes",
          [f["state"] for f in optimize.analyse(None, dict(EMPTY_HIST), lost, None)], ["OBSERVED"])
    check("a ledger that exists and cannot be read is not 'no ledger'",
          (optimize.load_ledger(ledger_dir) or {}).get("rejected"), 1)

    print("\nR142_13 - a status that promised a candidate and could not write one")
    fail_dir = tempfile.mkdtemp(dir=d)
    findings = optimize.analyse(None, {"comparable": good_rows, "total": 6, "in_scope": 6,
                                       "rejected": {}, "dropped": [], "time_order": "ok"},
                                None, None)
    blocked = [f["candidate_id"] for f in findings if f["state"] == "CANDIDATE"][0]
    open(os.path.join(fail_dir, blocked), "w").write("a file where a directory must go")
    hist_file = write(os.path.join(fail_dir, "h.jsonl"), good_rows)
    argv = [sys.executable, OPT, "--history", hist_file, "--ledger",
            os.path.join(fail_dir, "none.jsonl"), "--scan", "--emit-candidate", fail_dir,
            "--json", "--strict-exit"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    jf = json.loads(proc.stdout)
    check("nothing landed, so the status does not claim it did", jf["status"], "INTERNAL_ERROR")
    check("and the exit code follows the status", proc.returncode, 50)
    check("the failure is named", len(jf["candidates_failed"]), 1)

    # ---------------------------------------------------------------- positive controls
    print("\npositive controls - a gate that refuses everything is not a gate")
    good = good_rows
    case("P1 clean COMPLETE population", good, "CANDIDATE", 10, 1, comparable=6,
         history_quality="COMPLETE")
    case("P3 an invalid record in ANOTHER scope does not poison this one",
         good + [rec(9, 55.0, quality="INVALID", sessions=0, scope="other")],
         "CANDIDATE", 10, 1, comparable=6)
    envelope = json.dumps({"envelope": {"schema_version": 4, "run_id": "x"},
                           "payload": {}, "certificate": {}})
    rc, j, n = run([envelope])
    check("P4 current-generation evidence stays unsupported", j["status"], "INSUFFICIENT_DATA")
    check("P4 strict exit", rc, 20)
    check("P4 refused by name, not consumed",
          any("current-generation" in k for k in j["history"]["rejected"]), True)
    check("P4 nothing written", n, 0)
    check("P4 the supported schema set is unchanged", j["history_schema_supported"], [0, 1, 2])
    flat = [rec(i, 50.0) for i in range(6)]
    case("S_NOACTION nothing moved", flat, "NO_ACTION", 0, 0, comparable=6)
    case("S_LOCK another run holds the lock", good, "ALREADY_RUNNING", 41, 0, lock=True)

    # ---------------------------------------------------------------- the emission gate itself
    print("\nthe gate is in the emitter, not only in its caller")
    f = optimize.finding("x", "CANDIDATE", "head", "ev", scope="s", bucket=1)
    for status in ("PARTIAL_EVIDENCE", "HOST_BEHAVIOR_SHIFT", "INSUFFICIENT_DATA",
                   "INTERNAL_ERROR", "ALREADY_RUNNING", "NO_ACTION"):
        out = os.path.join(d, "gate_" + status)
        w, e, fail = optimize.emit_candidates([f], out, status)
        check(f"{status} writes nothing", (w, e, fail, os.path.exists(out)), ([], [], [], False))
    out = os.path.join(d, "gate_CANDIDATE")
    w, _e, _f = optimize.emit_candidates([f], out, "CANDIDATE")
    check("CANDIDATE still writes", (len(w), os.path.exists(out)), (1, True))

    print(f"\n{P} PASS, {F} FAIL")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
