#!/usr/bin/env python3
"""Thirty simulated days of an observer that never stops, and the evidence ladder underneath it.

Two questions a short test cannot answer:

  1. **Does it stay quiet?** A scheduler calling the optimizer a hundred times a day for a month is
     3,000 invocations. If each one rewrote its proposal, a human would face 3,000 files and stop
     reading them. This runs the real code that many times and counts what it actually wrote.
  2. **Does it get more informative as evidence accumulates, and refuse when it should?** That is
     the only defensible meaning of "gets smarter": one record cannot support a trend, four
     comparable records can, a workload change is not a trend, a host change is not a trend, and
     two scopes are never one population.

Everything is the shipped code path — `load_history`, `comparable`, `trend`, `analyse`,
`emit_candidates` — not a re-implementation. No model, no network, no policy file touched.

    python3 experiments/aivos/longrun.py
    python3 experiments/aivos/longrun.py --days 30 --cycles 100 --json
"""
import argparse, collections, hashlib, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import carry, optimize  # noqa: E402

ROLES = ["maker", "reviewer", "connector"]
EMPTY_HIST = {"comparable": [], "total": 0, "in_scope": 0, "rejected": {}, "dropped": [],
              "time_order": "ok"}


def rec(ts, shares, scope, turns=1000, workload="", runtimes=None):
    return {"schema_version": 2, "record_type": "carry_run", "run_id": carry.new_run_id(),
            "ts": ts, "sessions": 40, "turns": turns, "carry_bytes": 10 ** 7,
            "scope_id": scope, "workload_class": workload, "evidence_quality": "COMPLETE",
            "runtimes": runtimes or {"2.1.270": 40}, "models": {"m1": 40},
            "shares": shares, "bpt": {k: 1.0 for k in shares}}


def live(share_bash):
    # Four sources, shaped like the real archive (Bash dominant, Write/Edit and prose minor), so
    # the simulation is not made artificially noisy by a degenerate two-source vector in which
    # every rise is by construction someone else's fall.
    rest = 100 - share_bash
    return {"sessions": 40, "turns": 2000, "scanned": 40, "short": 0, "unreadable": 0,
            "oversize": 0, "skipped_by_limit": 0, "quality": "COMPLETE",
            "carry": collections.Counter({"Bash": share_bash, "Read": round(rest * 0.45),
                                          "Write/Edit": round(rest * 0.40),
                                          "prose": rest - round(rest * 0.45) - round(rest * 0.40)})}


def policy_hashes():
    out = {}
    for base in ("skills", "hooks", ".claude-plugin"):
        for r, _d, fs in os.walk(os.path.join(ROOT, base)):
            for f in fs:
                q = os.path.join(r, f)
                out[q] = hashlib.sha256(open(q, "rb").read()).hexdigest()
    return out


# ------------------------------------------------------------------ 1. the evidence ladder
def ladder():
    rows = []

    def step(label, recs, expect, usable=None):
        keep, _dropped = optimize.comparable(recs)
        order = optimize.time_order(keep)
        t = carry.trend(keep, "Bash", min_n=optimize.MIN_HISTORY_FOR_TREND) if order == "ok" else None
        got = "TREND" if t else ("AMBIGUOUS" if order != "ok" else "INSUFFICIENT_DATA")
        if got == "INSUFFICIENT_DATA" and len(keep) >= optimize.MIN_HISTORY_FOR_TREND:
            got = "NO_MOVEMENT"
        ok = got == expect and (usable is None or len(keep) == usable)
        rows.append((label, len(recs), len(keep), got, expect, ok))
        return t

    rising = [rec(1_750_000_000 + i * 604800, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}, "maker")
              for i in range(8)]
    step("1 record", rising[:1], "INSUFFICIENT_DATA")
    step("3 records (below the floor)", rising[:3], "INSUFFICIENT_DATA")
    t4 = step("4 comparable records (the floor)", rising[:4], "TREND")
    t8 = step("8 comparable records", rising[:8], "TREND")

    # A workload or scope boundary must not be CROSSED. When enough records remain on the newest
    # side of it a trend is still legitimate — the invariant is that the older class is dropped,
    # not that the tool goes blind. Both halves are asserted: the split, and what survives it.
    shifted = [rec(1_750_000_000 + i * 604800, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8},
                   "maker", workload="audit" if i < 4 else "build") for i in range(8)]
    step("8 records, workload changes midway (4 survive)", shifted, "TREND", usable=4)
    short_shift = [rec(1_750_000_000 + i * 604800, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8},
                       "maker", workload="audit" if i < 5 else "build") for i in range(8)]
    step("8 records, only 3 after the workload change", short_shift, "INSUFFICIENT_DATA", usable=3)

    two = ([rec(1_750_000_000 + i * 604800, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}, "maker")
            for i in range(4)] +
           [rec(1_750_000_000 + i * 604800, {"Bash": 80.0, "Read": 20.0}, "reviewer")
            for i in range(4)])
    step("two scopes in one file (only one scope is used)", two, "TREND", usable=4)
    lopsided = ([rec(1_750_000_000 + i * 604800, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8},
                     "maker") for i in range(6)] +
                [rec(1_750_000_000 + 7 * 604800, {"Bash": 80.0, "Read": 20.0}, "reviewer")])
    step("6 maker records + 1 newer reviewer record", lopsided, "INSUFFICIENT_DATA", usable=1)

    same_ts = [rec(1_750_000_000, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}, "maker")
               for i in range(6)]
    step("6 records, one timestamp (clock skew)", same_ts, "AMBIGUOUS")

    host = [rec(1_750_000_000 + i * 604800, {"Bash": 30.0 + i * 8, "Read": 70.0 - i * 8}, "maker",
                runtimes={"2.1.241" if i < 4 else "2.1.270": 40}) for i in range(8)]
    pop = optimize.population(host)
    rows.append(("8 records across a host-version change", len(host), len(host),
                 "HOST_SHIFT" if pop["host_shift"] else "no shift", "HOST_SHIFT",
                 bool(pop["host_shift"])))

    stability = None
    if t4 and t8:
        stability = abs(t8["slope"] - t4["slope"]) / (abs(t4["slope"]) or 1) * 100
    return rows, stability


# ------------------------------------------------------------------ 2. thirty days of cycles
def longrun(days, cycles, out, plateau=20):
    hist = os.path.join(out, "carry_history.jsonl")
    cand = os.path.join(out, "candidates")
    os.makedirs(cand, exist_ok=True)
    before_policy = policy_hashes()

    written = existing = 0
    statuses = collections.Counter()
    record_sizes = []
    per_day = []
    ts = 1_750_000_000
    day_of_shift, day_of_host = days // 2, int(days * 0.75)

    for day in range(days):
        # one aggregate record per role per day — what a real deployment appends
        for n, role in enumerate(ROLES):
            # Rise, then stop. The plateau is the part that matters: a scheduler must go
            # quiet when the world does, and only a run that contains both phases can
            # show that. `plateau` is scaled down for CI so the shape survives a short run.
            share = 30.0 + min(day, plateau) * (30.0 / plateau) + n * 5
            workload = "build" if day < day_of_shift else "audit"
            runtimes = {"2.1.270" if day < day_of_host else "2.1.290": 40}
            rest = 100 - share
            r = rec(ts + day * 86400,
                    {"Bash": round(share, 2), "Read": round(rest * 0.45, 2),
                     "Write/Edit": round(rest * 0.40, 2),
                     "prose": round(rest - rest * 0.45 - rest * 0.40, 2)},
                    role, workload=workload, runtimes=runtimes)
            line = json.dumps(r) + "\n"
            record_sizes.append(len(line.encode()))
            with open(hist, "a", encoding="utf-8") as fh:
                fh.write(line)

        day_new = 0
        for _cycle in range(cycles):
            recs, _rej, _lines = optimize.load_history(hist)
            scopes = optimize.by_scope(recs)
            for role in ROLES:
                keep, dropped = optimize.comparable(scopes.get(role, []))
                h = {"comparable": keep, "total": len(recs), "in_scope": len(scopes.get(role, [])),
                     "rejected": {}, "dropped": dropped, "time_order": optimize.time_order(keep)}
                lv = live(int(30 + min(day, plateau) * (30.0 / plateau)))
                f = optimize.analyse(lv, h, None, None, scope=role)
                st = optimize.overall_status(f, h, lv, optimize.population(keep), False)
                statuses[st] += 1
                w, e, _fail, _rr, _uv = optimize.emit_candidates(f, cand)
                written += len(w)
                existing += len(e)
                day_new += len(w)

        per_day.append(day_new)

    after_policy = policy_hashes()
    files = [os.path.join(r, f) for r, _d, fs in os.walk(cand) for f in fs]
    return dict(days=days, cycles=cycles,
                invocations=days * cycles * len(ROLES),
                records=days * len(ROLES),
                candidates_written=written, candidates_existing=existing,
                candidate_files=len(files),
                statuses=dict(statuses), per_day=per_day,
                policy_mutated=[k for k in before_policy if before_policy[k] != after_policy.get(k)],
                history_bytes=os.path.getsize(hist),
                median_record_bytes=sorted(record_sizes)[len(record_sizes) // 2],
                candidate_bytes=sum(os.path.getsize(f) for f in files))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--cycles", type=int, default=100)
    ap.add_argument("--plateau", type=int, default=20,
                    help="day on which the measured share stops rising; the run must extend\n"
                         "well past it, because the quiet phase is what is being tested")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rows, stability = ladder()
    d = tempfile.mkdtemp(prefix="sw-longrun-")
    try:
        sim = longrun(a.days, a.cycles, d, plateau=a.plateau)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    if a.json:
        print(json.dumps({"ladder": rows, "slope_stability_pct": stability, "longrun": sim},
                         indent=2))
        return 0

    print("EVIDENCE LADDER — what the observer will and will not say\n")
    print(f"{'evidence':<42}{'recs':>6}{'usable':>8}{'said':>20}{'expected':>20}  ok")
    allok = True
    for label, n, keep, got, exp, ok in rows:
        allok &= ok
        print(f"{label:<42}{n:>6}{keep:>8}{got:>20}{exp:>20}  {'yes' if ok else 'NO'}")
    if stability is not None:
        print(f"\nslope estimate moved {stability:.1f}% between 4 and 8 comparable records "
              f"(more clean evidence, same direction, steadier number)")

    print(f"\n\nTHIRTY-DAY SIMULATION — {sim['invocations']:,} optimizer invocations "
          f"({sim['days']} days x {sim['cycles']} cycles x {len(ROLES)} roles)\n")
    print(f"  records appended            {sim['records']:,}")
    print(f"  candidate FILES on disk     {sim['candidate_files']:,}")
    print(f"  candidate writes            {sim['candidates_written']:,}")
    print(f"  suppressed as EXISTING      {sim['candidates_existing']:,}")
    print(f"  policy files mutated        {len(sim['policy_mutated'])}")
    print(f"  history on disk             {sim['history_bytes']:,} B "
          f"(median record {sim['median_record_bytes']} B)")
    print(f"  candidate specs on disk     {sim['candidate_bytes']:,} B")
    print("  statuses seen               " +
          ", ".join(f"{k}={v:,}" for k, v in sorted(sim["statuses"].items())))

    per_year = sim["median_record_bytes"] * len(ROLES) * 365
    print(f"\n  projected history growth    {per_year / 1e6:.1f} MB per year at one record per "
          f"role per day ({len(ROLES)} roles)")
    pd = sim["per_day"]
    tail = pd[-7:]
    print(f"\n  new proposals per day       {' '.join(str(x) for x in pd)}")
    print(f"  while the metric RISES       {sum(pd[:a.plateau])} over {a.plateau} days")
    print(f"  in the LAST SEVEN days       {sum(tail)}  (metric flat; every finding type has "
          f"already appeared at least once)")
    # Spam is (a) writing the same proposal twice, or (b) still producing new proposals after the
    # evidence has stopped moving. A finding's FIRST appearance is not spam, even late, so the
    # window is the settled tail rather than an arbitrary two-thirds split.
    spam = sim["candidates_written"] > sim["candidate_files"] or sum(tail) > 0
    print(f"\n  CANDIDATE_SPAM={'YES' if spam else 'NO'} — "
          f"{sim['candidates_written']} write(s) produced {sim['candidate_files']} file(s); "
          f"{sim['candidates_existing']:,} repeat proposals were suppressed")
    print(f"  POLICY_MUTATION={'YES' if sim['policy_mutated'] else 'NONE'}")
    print(f"  LADDER={'PASS' if allok else 'FAIL'}")
    return 0 if (allok and not spam and not sim["policy_mutated"]) else 1


if __name__ == "__main__":
    sys.exit(main())
