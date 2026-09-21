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


def main():
    d = tempfile.mkdtemp(prefix="sw-142-fx-")

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
          optimize.promotable("PARTIAL", True), True)
    check("--accept-partial does not accept a loss",
          optimize.promotable("DEGRADED", True), False)
    check("--accept-partial does not accept what cannot be verified",
          optimize.promotable("UNKNOWN", True), False)
    check("--accept-partial does not accept an invalid record",
          optimize.promotable("INVALID", True), False)
    check("COMPLETE needs no flag", optimize.promotable("COMPLETE", False), True)
    check("PARTIAL without the flag stays refused", optimize.promotable("PARTIAL", False), False)

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
          optimize.promotable(optimize.sweep_quality(a_torn), True), False)
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

    # ---------------------------------------------------------------- U1
    print("\nU1 - a generation that never had the field cannot have defaulted to COMPLETE")
    old = [rec(i, 30.0 + 3.0 * i, schema=1, counters=False) for i in range(6)]
    case("U1", old, "PARTIAL_EVIDENCE", 40, 0, comparable=6, history_quality="UNKNOWN")
    case("U1 (--accept-partial does not rescue it)", old, "PARTIAL_EVIDENCE", 40, 0,
         extra=["--accept-partial"])

    # ---------------------------------------------------------------- positive controls
    print("\npositive controls - a gate that refuses everything is not a gate")
    good = [rec(i, 30.0 + 3.0 * i) for i in range(6)]
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
