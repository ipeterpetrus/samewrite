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
          optimize.record_quality(rec(0, 40.0, quality="PARTIAL", skipped=5)), "PARTIAL")
    check("...but a PARTIAL claim no counter can explain is not a bound to adopt",
          optimize.record_quality(rec(0, 40.0, quality="PARTIAL")), "UNKNOWN")
    check("and the flag does not adopt it either",
          optimize.may_promote(optimize.record_quality(rec(0, 40.0, quality="PARTIAL")), True),
          False)
    for counter in ("malformed", "malformed_lines", "identity_changed", "conflicted_sources",
                    "records_rejected"):
        check(f"a record carrying {counter} is not COMPLETE",
              optimize.record_quality(dict(rec(0, 40.0), **{counter: 1})), "DEGRADED")
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
    recs, rejected, _lines, _ep = optimize.load_history(hist_path)
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
    # Expectation updated by the B1 repair (docs/V142_COUNTEREXAMPLES.md §5.1): the loss still
    # refuses the records it followed — nothing is promoted and nothing is written — but it is a
    # BOUNDARY, not a verdict on the file, so the status is "no epoch to analyse" rather than a
    # permanent PARTIAL_EVIDENCE that no later evidence could ever clear.
    torn_hist = [json.dumps(r) for r in good_rows] + ['{"torn":']
    j = case("R142_11", torn_hist, "INSUFFICIENT_DATA", 20, 0, history_quality="EMPTY")
    check("the torn line is still counted", j["history"]["rejected"].get("unparseable line"), 1)
    check("and the file's loss is named", (j["history"].get("damage") or {}).get("boundaries"), 1)
    case("R142_11 (--accept-partial does not adopt a loss)", torn_hist,
         "INSUFFICIENT_DATA", 20, 0, extra=["--accept-partial"])
    check("the records BEFORE the loss cannot support a promotion after it",
          run([json.dumps(r) for r in good_rows] + ['{"torn":']
              + [json.dumps(rec(i, 30.0 + 3.0 * i)) for i in range(20, 22)])[1]["history"]["comparable"],
          2)
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

    print("\nR142_14 - the scope fallback is a label on an empty run, not a way back in")
    only_bad = [{"schema_version": 2, "record_type": "carry_run", "ts": TS0, "sessions": 0,
                 "scanned": 1, "scope_id": "attack", "evidence_quality": "INVALID",
                 "shares": {"Bash": 100.0}}]
    j = case("R142_14 (nothing eligible anywhere)", only_bad, "PARTIAL_EVIDENCE", 40, 0,
             comparable=0)
    check("the scope it names is the one real record's scope", j["scope"]["analysed"], "attack")
    prod = [dict(r, scope_id="prod", run_id="prod%d" % i) for i, r in enumerate(good_rows)]
    j2 = case("R142_14 (an eligible population is never stranded by it)", prod + only_bad,
              "CANDIDATE", 10, 1, comparable=6)
    check("and the eligible population chooses the scope", j2["scope"]["analysed"], "prod")

    print("\nR142_15 - a rejected line is damage unless it is one of the named exceptions")
    for line, label, status, quality in (
            ('{"schema_version":3,"record_type":"carry_run","shares":{"Bash":60.0,"Read":40.0}}',
             "a record from a schema this reader does not know", "INSUFFICIENT_DATA", "EMPTY"),
            ('{"schema_version":2,"record_type":"carry_run","shares":{"Bash":10.0}}',
             "a carry record whose shares do not sum to a population", "INSUFFICIENT_DATA",
             "EMPTY"),
            ('{"note": "another tool\'s line in a shared file"}',
             "a line that was never a carry record", "CANDIDATE", "COMPLETE")):
        code = {"INSUFFICIENT_DATA": 20, "PARTIAL_EVIDENCE": 40, "CANDIDATE": 10}[status]
        case(f"R142_15: {label}", [json.dumps(r) for r in good_rows] + [line],
             status, code, 1 if status == "CANDIDATE" else 0, history_quality=quality)
        if status != "CANDIDATE":
            # the same rejected line BEFORE a healthy population: the loss cuts, it does not kill
            case(f"R142_15: {label} — and a population after it still stands",
                 [line] + [json.dumps(r) for r in good_rows], "CANDIDATE", 10, 1,
                 comparable=6, history_quality="COMPLETE")

    print("\nR142_16 - a ledger line that is neither a write nor a denial is a line lost")
    led_dir = tempfile.mkdtemp(dir=d)
    unknown_event = os.path.join(led_dir, "unknown.jsonl")
    with open(unknown_event, "w", encoding="utf-8") as fh:
        fh.write("\n".join('{"event": "checked"}' for _ in range(100)) + "\n")
        fh.write('{"event": "garbage"}\n')
    led = optimize.load_ledger(unknown_event)
    check("the unaccountable line is counted", (led["writes"], led["rejected"]), (100, 1))
    check("and the guard only observes",
          [f["state"] for f in optimize.analyse(None, dict(EMPTY_HIST), led, None)], ["OBSERVED"])

    print("\nR142_18 - round-4 findings: the live sweep, the shares reason, the temp file")
    live_impossible = {"sessions": 40, "turns": 0, "scanned": 40, "unreadable": 0, "oversize": 0,
                       "skipped_by_limit": 0, "malformed": 0, "identity_changed": 0,
                       "conflicted_sources": 0, "quality": "COMPLETE"}
    check("a live sweep with sessions and no turns is impossible too",
          optimize.sweep_quality(live_impossible), "INVALID")
    check("control: the same sweep with turns is COMPLETE",
          optimize.sweep_quality(dict(live_impossible, turns=2000)), "COMPLETE")
    claims_ours = json.dumps({"schema_version": 2, "record_type": "carry_run", "ts": TS0,
                              "sessions": 40, "turns": 1000, "carry_bytes": 10 ** 7})
    case("R142_18: a carry record with no shares key at all is a loss",
         [json.dumps(r) for r in good_rows] + [claims_ours],
         "INSUFFICIENT_DATA", 20, 0, history_quality="EMPTY")
    case("R142_18: ...and a population after that loss still stands",
         [claims_ours] + [json.dumps(r) for r in good_rows], "CANDIDATE", 10, 1,
         comparable=6, history_quality="COMPLETE")
    tmp_dir = tempfile.mkdtemp(dir=d)
    blocked_id = [f["candidate_id"] for f in optimize.analyse(
        None, {"comparable": good_rows, "total": 6, "in_scope": 6, "rejected": {}, "dropped": [],
               "time_order": "ok"}, None, None) if f["state"] == "CANDIDATE"][0]
    open(os.path.join(tmp_dir, blocked_id), "w").write("a file where a directory must go")
    hist2 = write(os.path.join(tmp_dir, "h.jsonl"), good_rows)
    subprocess.run([sys.executable, OPT, "--history", hist2, "--ledger",
                    os.path.join(tmp_dir, "none.jsonl"), "--scan", "--emit-candidate", tmp_dir,
                    "--json", "--strict-exit"], capture_output=True, text=True, timeout=300)
    check("a failed write leaves no half-written file behind",
          [f for _b, _dd, fs in os.walk(tmp_dir) for f in fs if ".tmp-" in f], [])
    bound_dir = tempfile.mkdtemp(dir=d)
    trio = []
    for n, name in enumerate(("p.jsonl", "q.jsonl", "r.jsonl")):
        q = transcript(os.path.join(bound_dir, name), turns=30)
        os.utime(q, (TS0 + n * 1000, TS0 + n * 1000))
        trio.append(q)
    once = carry.bounded_paths(trio, 2)
    swept = carry.accumulate(trio, min_turns=1, max_files=2, selected=once)
    check("a caller can hand the sweep the selection it already made",
          sorted(os.path.basename(x) for x in swept["parsed"]),
          sorted(os.path.basename(x) for x in once))
    check("and the bound is still reported against the whole population",
          swept["skipped_by_limit"], 1)

    # ============================================================ B1: the history epoch
    # An unattributable loss cuts the promotion history at that physical position. Evidence before
    # the cut never joins evidence after it; the loss stays reported; the newest epoch is, by
    # construction, free of damage. docs/V142_COUNTEREXAMPLES.md §5 froze every row below.
    print("\nB1 - a damaged history recovers, and the loss is still reported")
    TORN = '{"schema_version": 2, "record_type": "carry_run", "ts": 1750000000, "sessions": 5'
    FOREIGN = json.dumps({"note": "another tool's line in a shared file"})
    ENVELOPE = json.dumps({"envelope": {"schema_version": 4, "run_id": "x"}, "payload": {},
                           "certificate": {}})

    def series(n, first=0, scope="default", per_week=3.0, base=30.0):
        return [json.dumps(rec(first + i, base + per_week * i, scope=scope)) for i in range(n)]

    def b1(label, rows, status, code, files, comparable, epoch, quality, boundaries, extra=()):
        rc, j, n = run(rows, extra=extra)
        got = (j["status"], rc, n, j["history"]["comparable"],
               j["scope"].get("records_in_epoch"), j["history"].get("quality"),
               (j["history"].get("damage") or {}).get("boundaries"))
        check(label, got, (status, code, files, comparable, epoch, quality, boundaries))

    b1("B1_01 loss at the tail leaves no epoch to promote from",
       series(6) + [TORN], "INSUFFICIENT_DATA", 20, 0, 0, 0, "EMPTY", 1)
    b1("B1_02 an epoch too small to carry a trend",
       series(6) + [TORN] + series(2, 20), "INSUFFICIENT_DATA", 20, 0, 2, 2, "COMPLETE", 1)
    b1("B1_03 a sufficient post-loss epoch promotes on its own",
       series(6) + [TORN] + series(6, 20), "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 1)
    b1("B1_04 and it still promotes sixty records later",
       series(6) + [TORN] + series(60, 20, per_week=1.0, base=20.0),
       "CANDIDATE", 10, 1, 60, 60, "COMPLETE", 1)
    b1("B1_05 an unattributable loss cuts every scope (analysing the recovered one)",
       series(6, scope="agent-a") + [TORN] + series(6, 20, scope="agent-b"),
       "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 1)
    b1("B1_05b ...and the scope with nothing after the loss says so",
       series(6, scope="agent-a") + [TORN] + series(6, 20, scope="agent-b"),
       "INSUFFICIENT_DATA", 20, 0, 0, 0, "EMPTY", 1, extra=["--scope-id", "agent-a"])
    b1("B1_06 two boundaries: only the newest epoch is analysed",
       series(6) + [TORN] + series(6, 20) + [TORN] + series(6, 40),
       "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 2)
    b1("B1_07 a loss before any record does not stop the file",
       [TORN] + series(6), "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 1)
    b1("B1_09 a foreign line is not a loss",
       series(6) + [FOREIGN], "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 0)
    b1("B1_10 current-generation evidence refused by design is not a loss",
       series(6) + [ENVELOPE], "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 0)
    b1("B1_12 records the law calls INVALID are refused, not a loss",
       [json.dumps(rec(i, 30.0 + 3.0 * i, sessions=0, scanned=40)) for i in range(6)],
       "PARTIAL_EVIDENCE", 40, 0, 0, 6, "EMPTY", 0)

    # B1_08: a truncated final line, written the way a crash leaves one
    trunc_dir = tempfile.mkdtemp(dir=d)
    trunc = os.path.join(trunc_dir, "history.jsonl")
    with open(trunc, "w", encoding="utf-8") as fh:
        fh.write("\n".join(series(6)) + "\n")
        fh.write('{"schema_version": 2, "record_type": "carry_run", "ts": 17500000')
    out_dir = os.path.join(trunc_dir, "cand")
    proc = subprocess.run([sys.executable, OPT, "--history", trunc, "--ledger",
                           os.path.join(trunc_dir, "none.jsonl"), "--scan", "--emit-candidate",
                           out_dir, "--json", "--strict-exit"], capture_output=True, text=True,
                          timeout=300)
    jt = json.loads(proc.stdout)
    # the emit directory itself is created by the LOCK, before any status is known; what the
    # matrix froze is the candidate-FILE count
    spec_files = [f for _b, _dd, fs in os.walk(out_dir) for f in fs if f != ".optimize.lock"]
    check("B1_08 a truncated final line is the same loss",
          (jt["status"], proc.returncode, len(spec_files),
           (jt["history"].get("damage") or {}).get("boundaries")),
          ("INSUFFICIENT_DATA", 20, 0, 1))

    print("\nB1_11 / M2 - a zero-carry sweep is readable evidence, not corruption")
    zero_carry = dict(rec(9, 0.0), shares={}, bpt={}, carry_bytes=0)
    ok, why = optimize.valid_record(zero_carry)
    check("the reader accepts the shape the producer writes", (ok, why), (True, ""))
    check("and the quality law calls it EMPTY, not INVALID",
          optimize.record_quality(zero_carry), "EMPTY")
    b1("B1_11 one zero-carry record does not stop a healthy population",
       series(6) + [json.dumps(zero_carry)], "CANDIDATE", 10, 1, 6, 7, "COMPLETE", 0)
    b1("B1_11b a history of nothing but zero-carry records is not damage",
       [json.dumps(dict(rec(i, 0.0), shares={}, bpt={}, carry_bytes=0)) for i in range(6)],
       "INSUFFICIENT_DATA", 20, 0, 0, 6, "EMPTY", 0)
    check("carry with no shares is still a contradiction",
          optimize.record_quality(dict(rec(9, 40.0), carry_bytes=0)), "INVALID")
    check("shares with no carry is still a contradiction",
          optimize.record_quality(dict(rec(9, 40.0), shares={}, bpt={})), "INVALID")
    # the producer's own words, executed: a session whose items all land on its last turn
    zt = os.path.join(d, "zero_carry.jsonl")
    with open(zt, "w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps({"type": "assistant", "message": {
                "id": f"t{i}", "usage": {"output_tokens": 3}, "content": []}}) + "\n")
        fh.write(json.dumps({"type": "assistant", "message": {
            "id": "last", "usage": {"output_tokens": 3},
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}}) + "\n")
    zsweep = carry.accumulate([zt], min_turns=1)
    check("the producer really can measure zero carry",
          (zsweep["sessions"] > 0, sum(zsweep["carry"].values())), (True, 0))

    print("\nB1_13 - one run_id on both sides of a boundary")
    dup_before = series(5) + [json.dumps(dict(json.loads(series(1, 5)[0]), run_id="carried"))]
    dup_after = [json.dumps(dict(json.loads(r), run_id="carried" if i == 0 else None))
                 for i, r in enumerate(series(6, 20))]
    dup_after = [json.dumps({k: v for k, v in json.loads(r).items() if v is not None})
                 for r in dup_after]
    b1("B1_13 the post-loss epoch keeps its own copy",
       dup_before + [TORN] + dup_after, "CANDIDATE", 10, 1, 6, 6, "COMPLETE", 1)
    same_epoch = series(5) + [json.dumps(dict(json.loads(series(1, 5)[0]), run_id="twin")),
                              json.dumps(dict(json.loads(series(1, 6)[0]), run_id="twin",
                                              evidence_quality="PARTIAL", skipped_by_limit=9))]
    rc, j, n = run(same_epoch)
    check("B1_13b a retry inside one epoch still lowers the survivor",
          (j["history"]["quality"], j["status"], n), ("PARTIAL", "PARTIAL_EVIDENCE", 0))
    # both line orders, because which copy comes first is exactly what a crash decides
    clean_then_worse = (series(5) + [json.dumps(dict(rec(5, 45.0), run_id="X"))] + [TORN]
                        + [json.dumps(dict(rec(6, 45.0), run_id="X", evidence_quality="PARTIAL",
                                           skipped_by_limit=9))]
                        + series(5, 21))
    rc, j, n = run(clean_then_worse)
    check("B1_13c the post-loss copy is judged on its OWN evidence",
          j["history"]["quality"], "PARTIAL")
    worse_then_clean = (series(5)
                        + [json.dumps(dict(rec(5, 45.0), run_id="X", evidence_quality="PARTIAL",
                                           skipped_by_limit=9))] + [TORN]
                        + [json.dumps(dict(rec(6, 45.0), run_id="X"))] + series(5, 21))
    rc, j, n = run(worse_then_clean)
    check("B1_13d and an excluded pre-loss copy does not poison it",
          (j["history"]["quality"], j["status"] == "PARTIAL_EVIDENCE"), ("COMPLETE", False))
    three_in_one = series(4) + [json.dumps(dict(rec(4, 42.0), run_id="S")),
                                json.dumps(dict(rec(5, 45.0), run_id="S", unreadable=1)),
                                json.dumps(dict(rec(6, 48.0), run_id="S",
                                                evidence_quality="PARTIAL", skipped_by_limit=4))]
    rc, j, n = run(three_in_one)
    check("B1_13e three copies inside one epoch: the worst of them survives",
          (j["history"]["quality"], j["history"]["rejected"].get("duplicate run_id (retry)"), n),
          ("DEGRADED", 2, 0))

    print("\nM1 - history.quality describes the evidence eligible RIGHT NOW")
    rc, j, n = run([json.dumps(rec(i, 30.0 + 3.0 * i, sessions=0, scanned=40)) for i in range(6)])
    check("nothing comparable is never reported as COMPLETE",
          (j["history"]["comparable"], j["history"]["quality"]), (0, "EMPTY"))

    print("\nthe damage is reported even while the current epoch is clean")
    rc, j, n = run(series(6) + [TORN] + series(6, 20))
    check("the rejection is still counted", j["history"]["rejected"].get("unparseable line"), 1)
    check("and the file's historical damage is named",
          ((j["history"].get("damage") or {}).get("boundaries"),
           (j["history"].get("damage") or {}).get("file_global")), (1, 1))
    check("while the analysed epoch is clean and promotes",
          (j["history"]["quality"], j["status"]), ("COMPLETE", "CANDIDATE"))

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
