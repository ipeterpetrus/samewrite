#!/usr/bin/env python3
"""Offline optimizer: read the aggregate evidence SameWrite already keeps, say where cost is
concentrated, what moved, and whether any of it is strong enough to justify an experiment.

    python3 tools/optimize.py                          # every profile on this machine + default ledger
    python3 tools/optimize.py --history ~/logs/carry_history.jsonl --json
    python3 tools/optimize.py --emit-candidate experiments/candidates

It calls no model, opens no socket, and writes nothing into any model's context. It reuses
`tools/carry.py` (live scan, history schema, trend) and the guard ledger — there is no second
telemetry channel. It never edits `skills/`, `hooks/` or any policy file: its output is a
report and, on request, a candidate specification for a human to decide about.

THRESHOLDS ARE FIXED BELOW, BEFORE ANY REAL OUTCOME WAS READ. A finding that does not clear
its threshold is reported as insufficient evidence, and `NO_ACTION` is a successful run: the
optimizer exists to refuse an optimization the data cannot support.
"""
import argparse, collections, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import carry  # noqa: E402  (live scan, trend, history schema — reused, not duplicated)
import skills as skills_tool  # noqa: E402  (listing usage — reused)

# ---------------------------------------------------------------- frozen thresholds
MIN_SESSIONS = 20            # a share is a property of a corpus, not of one session
MIN_TURNS = 500
CONCENTRATION_SHARE = 25.0   # % of carry before "cost is concentrated here" is sayable
MIN_HISTORY_FOR_TREND = 4    # three points make a guess wearing a number (carry.trend's own floor)
TREND_MIN_SLOPE = 2.0        # percentage points per month — the SUSTAINED-shift signal
TREND_MIN_Z = 2.0            # last value this far outside its own history — the SPIKE signal.
                             # These are alternatives, not a conjunction: a clean linear rise of
                             # six points has z ~= 1.5 by construction, so requiring both would
                             # have reported only spikes and called them trends (caught by
                             # tests/test_optimize.py before this tool ever ran on real data).
CORPUS_TURN_RATIO_MAX = 1.5  # same comparability rule the history writer uses
LEDGER_MIN_WRITES = 100      # the README's own falsification sample for the guard
LEDGER_MIN_NOOP_RATE = 2.0   # % — below this over a full sample the guard stops paying
COLD_LISTING_MIN_SHARE = 30.0
COLD_LISTING_MIN_BYTES = 5000
SEGMENT_MIN_SESSIONS = 10    # below this a per-model claim is noise with a label
HOST_SHIFT_MIN_MOVE = 5.0    # pp move across a runtime change = populations are not one world

SCHEMA_SUPPORTED = (0, 1)    # 0 = pre-1.2 records without a schema field
STATES = ("OBSERVED", "HYPOTHESIS", "CANDIDATE", "EXPERIMENTAL", "PROVEN", "REJECTED")
SOURCE_HINT = {
    "Bash": ("bash-output-shaping", "ask Bash for the answer, not the log: failures-only, bounded "
             "output, counts instead of listings", "skill body (no always-on bytes)"),
    "Read": ("read-range-discipline", "read a range or a symbol, not a whole file", "skill body (no always-on bytes)"),
    "injected": ("listing-prune", "remove listing entries that are never invoked", "user configuration, not SameWrite text"),
    "prose": ("output-economy", "shorter answers where nothing is lost", "skill body (no always-on bytes)"),
    "Write/Edit": ("edit-discipline", "anchored Edit under ~25% changed; never rewrite what is identical",
                   "skill body (no always-on bytes)"),
}


# ---------------------------------------------------------------- history: load and validate
def valid_record(o):
    """-> (ok, reason). Malformed input must not poison a trend; it must be counted and dropped."""
    if not isinstance(o, dict):
        return False, "not an object"
    if o.get("record_type") not in (None, "carry_run"):
        return False, "unknown record_type"
    sv = o.get("schema_version", 0)
    if not isinstance(sv, int) or sv not in SCHEMA_SUPPORTED:
        return False, f"unsupported schema_version {sv!r}"
    sh = o.get("shares")
    if not isinstance(sh, dict) or not sh:
        return False, "no shares"
    for k, v in sh.items():
        if not isinstance(k, str) or not isinstance(v, (int, float)) or isinstance(v, bool):
            return False, "non-numeric share"
        if v < 0 or v > 100.5:
            return False, "share out of range"
    tot = sum(sh.values())
    if not (95.0 <= tot <= 105.0):
        return False, f"shares sum to {tot:.1f}, not ~100"
    for k in ("ts", "turns", "sessions", "carry_bytes"):
        v = o.get(k)
        if v is None:
            continue
        if not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 10 ** 15:
            return False, f"implausible {k}"
    return True, ""


def load_history(path):
    recs, rejected = [], collections.Counter()
    if not path or not os.path.exists(path):
        return recs, rejected, 0
    lines = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            lines += 1
            try:
                o = json.loads(line)
            except Exception:
                rejected["unparseable line"] += 1
                continue
            ok, why = valid_record(o)
            (recs.append(o) if ok else rejected.__setitem__(why, rejected[why] + 1))
    seen, uniq = set(), []
    for r in recs:                       # an identical record written twice is one observation
        k = (r.get("ts"), r.get("turns"), tuple(sorted(r.get("shares", {}).items())))
        if k in seen:
            rejected["duplicate record"] += 1
            continue
        seen.add(k)
        uniq.append(r)
    return uniq, rejected, lines


def comparable(recs):
    """Records whose corpus is close enough to the newest one to be compared at all."""
    if not recs:
        return [], []
    newest = max(recs, key=lambda r: r.get("ts") or 0)
    n_turn = newest.get("turns") or 0
    keep, dropped = [], []
    for r in recs:
        t = r.get("turns") or 0
        if n_turn and t and max(n_turn, t) / min(n_turn, t) > CORPUS_TURN_RATIO_MAX:
            dropped.append((r, f"corpus {t:,} turns vs {n_turn:,}"))
        else:
            keep.append(r)
    return keep, dropped


def clock_ok(recs):
    ts = [r.get("ts") or 0 for r in recs]
    return all(b >= a for a, b in zip(ts, ts[1:]))


def population(recs, live=None):
    """Runtime and model mix, and whether the population may be treated as one world."""
    runtimes, models = collections.Counter(), collections.Counter()
    for r in recs:
        runtimes.update({k: v for k, v in (r.get("runtimes") or {}).items() if isinstance(v, int)})
        models.update({k: v for k, v in (r.get("models") or {}).items() if isinstance(v, int)})
    if live:
        runtimes.update(live.get("runtimes") or {})
        models.update(live.get("models") or {})
    shift = None
    dated = sorted([r for r in recs if r.get("runtimes")], key=lambda r: r.get("ts") or 0)
    if len(dated) >= 2:
        first, last = dated[0], dated[-1]
        if set(first["runtimes"]) != set(last["runtimes"]):
            keys = set(first.get("shares", {})) & set(last.get("shares", {}))
            move = max((abs(last["shares"][k] - first["shares"][k]) for k in keys), default=0.0)
            if move >= HOST_SHIFT_MIN_MOVE:
                shift = (sorted(first["runtimes"]), sorted(last["runtimes"]), move)
    sessions = sum(r.get("sessions") or 0 for r in recs) or (live or {}).get("sessions", 0)
    if len(models) <= 1:
        verdict = "GLOBAL_SIGNAL" if sessions >= SEGMENT_MIN_SESSIONS else "INSUFFICIENT_DATA"
    else:
        verdict = "MODEL_SPECIFIC_SIGNAL" if sessions >= SEGMENT_MIN_SESSIONS * len(models) else "INSUFFICIENT_DATA"
    return {"runtimes": runtimes, "models": models, "host_shift": shift, "segmentation": verdict}


# ---------------------------------------------------------------- ledger (guard field data)
def load_ledger(path):
    checked = denied = 0
    rejected = 0
    if not path or not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                rejected += 1
                continue
            if not isinstance(o, dict):
                rejected += 1
                continue
            ev = o.get("event")
            if ev == "checked":
                checked += 1
            elif ev == "denied":
                denied += 1
    total = checked + denied
    return {"writes": total, "prevented": denied, "rejected": rejected,
            "rate": (100.0 * denied / total) if total else 0.0}


# ---------------------------------------------------------------- findings
def finding(cid, state, headline, evidence, hypothesis="", metric="", effect="", risk="",
            layer="", always_on_bytes=0, benchmark=""):
    return dict(id=cid, state=state, headline=headline, evidence=evidence, hypothesis=hypothesis,
                source_metric=metric, expected_effect=effect, risk=risk, affected_layer=layer,
                always_on_bytes_delta=always_on_bytes, benchmark_required=benchmark,
                date=time.strftime("%Y-%m-%d", time.gmtime()))


def analyse(live, hist, ledger, cold):
    out = []
    # 1. concentration — only sayable over a corpus, never over one session
    if live and live["sessions"]:
        C = sum(live["carry"].values()) or 1
        enough = live["sessions"] >= MIN_SESSIONS and live["turns"] >= MIN_TURNS
        for src, val in live["carry"].most_common():
            share = 100.0 * val / C
            if share < CONCENTRATION_SHARE:
                continue
            cid, fix, layer = SOURCE_HINT.get(src, (re.sub(r"[^a-z0-9]+", "-", src.lower()).strip("-"),
                                                     "reduce what this source leaves resident", "skill body"))
            ev = (f"{src} is {share:.1f}% of carry over {live['sessions']} sessions / "
                  f"{live['turns']:,} turns")
            if enough:
                out.append(finding(cid, "CANDIDATE", f"{src} dominates carry", ev,
                                   hypothesis=f"{fix} lowers total task cost without lowering correctness",
                                   metric=f"carry share of {src}", effect="unknown until measured",
                                   risk="a rule that shortens evidence can raise retries",
                                   layer=layer, always_on_bytes=0,
                                   benchmark="paired fixtures, correctness gate first, then total cost"))
            else:
                out.append(finding(cid, "OBSERVED", f"{src} dominates carry", ev + " — below the "
                                   f"{MIN_SESSIONS}-session / {MIN_TURNS}-turn floor",
                                   metric=f"carry share of {src}"))
    # 2. movement — needs a comparable history, not two points
    if hist["comparable"]:
        keys = set()
        for r in hist["comparable"]:
            keys.update(r.get("shares", {}))
        for k in sorted(keys):
            t = carry.trend(hist["comparable"], k, min_n=MIN_HISTORY_FOR_TREND)
            if not t:
                continue
            per_month = t["slope"] * 30.0
            if abs(per_month) >= TREND_MIN_SLOPE:
                cid = "trend-" + re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")
                spike = (" — but the last value sits z=%+.1f from its own history, so this slope "
                         "may be one spike rather than a shift" % t["z"]) if abs(t["z"]) >= TREND_MIN_Z else ""
                out.append(finding(cid, "CANDIDATE", f"{k} share is moving",
                                   f"{per_month:+.1f} pp/month over {t['n']} records, last value z={t['z']:+.1f}{spike}",
                                   hypothesis=f"the change in {k} is a shift, not a spike, and has a cause worth naming",
                                   metric=f"slope of {k} share", effect="unknown until measured",
                                   risk="a trend can come from the workload, not from SameWrite",
                                   layer="investigation only", always_on_bytes=0,
                                   benchmark="identify the cause before proposing a rule"))
    # 3. the guard: does it still pay for itself? (rule retirement is a first-class outcome)
    if ledger and ledger["writes"]:
        if ledger["writes"] >= LEDGER_MIN_WRITES:
            if ledger["rate"] >= LEDGER_MIN_NOOP_RATE:
                out.append(finding("noop-guard-retain", "OBSERVED", "the no-op guard is still paying",
                                   f"{ledger['prevented']} of {ledger['writes']} writes prevented "
                                   f"({ledger['rate']:.1f}% ≥ {LEDGER_MIN_NOOP_RATE}%)",
                                   metric="ledger deny rate"))
            else:
                out.append(finding("noop-guard-retire", "CANDIDATE", "the no-op guard may have stopped paying",
                                   f"{ledger['prevented']} of {ledger['writes']} writes prevented "
                                   f"({ledger['rate']:.1f}% < {LEDGER_MIN_NOOP_RATE}%)",
                                   hypothesis="the hook's cost is no longer covered by what it prevents; removing it "
                                              "is the change to test",
                                   metric="ledger deny rate", effect="one fewer PreToolUse hook",
                                   risk="a low field rate can be the read-then-write bypass, not absence of no-ops",
                                   layer="hook (removal)", always_on_bytes=0,
                                   benchmark="re-measure on a fresh sample before removing"))
        else:
            out.append(finding("noop-guard", "OBSERVED", "the guard's field sample is too small to judge",
                               f"{ledger['writes']} writes recorded, need {LEDGER_MIN_WRITES}",
                               metric="ledger deny rate"))
    # 4. the listing the user pays for on every turn
    if cold:
        share = 100.0 * cold["cold_bytes"] / (cold["total_bytes"] or 1)
        ev = (f"{cold['cold']}/{cold['entries']} entries never invoked, "
              f"{cold['cold_bytes']:,} of {cold['total_bytes']:,} listing bytes ({share:.1f}%)")
        if share >= COLD_LISTING_MIN_SHARE and cold["cold_bytes"] >= COLD_LISTING_MIN_BYTES:
            out.append(finding("listing-prune", "CANDIDATE", "most of the skill listing is never invoked", ev,
                               hypothesis="uninstalling never-invoked plugins removes always-on carry with no loss",
                               metric="cold share of the skill listing",
                               effect=f"~{cold['cold_bytes']:,} bytes per turn",
                               risk="a description can route without ever being loaded — an upper bound on waste",
                               layer="user configuration, not SameWrite text", always_on_bytes=-cold["cold_bytes"],
                               benchmark="uninstall one, measure the listing and the outcome"))
        else:
            out.append(finding("listing-prune", "OBSERVED", "skill listing is mostly used", ev,
                               metric="cold share of the skill listing"))
    return out


# ---------------------------------------------------------------- rendering
def render(live, hist, ledger, cold, pop, findings, sources):
    L = ["SameWrite Health — evidence-adaptive optimizer", ""]
    L.append("scope")
    L.append(f"  history   : {sources['history'] or '(none)'} — {hist['total']} records, "
             f"{len(hist['comparable'])} comparable, {sum(hist['rejected'].values())} rejected")
    for why, n in hist["rejected"].most_common():
        L.append(f"              rejected: {n} × {why}")
    for _, why in hist["dropped"][:3]:
        L.append(f"              not comparable: {why}")
    L.append(f"  ledger    : {sources['ledger'] or '(none)'} — "
             + (f"{ledger['writes']} writes, {ledger['prevented']} identical prevented" if ledger else "no records"))
    if live:
        L.append(f"  live scan : {live['sessions']} sessions / {live['turns']:,} turns "
                 f"({live['scanned']} transcripts, {live['short']} below the turn floor)")
    L.append("")
    if live and live["sessions"]:
        C = sum(live["carry"].values()) or 1
        L.append("where cost is concentrated (carry = size × turns remaining)")
        for src, val in live["carry"].most_common(6):
            L.append(f"  {src:<34} {100.0 * val / C:5.1f}%")
        L.append("")
    L.append("movement")
    if len(hist["comparable"]) < MIN_HISTORY_FOR_TREND:
        L.append(f"  INSUFFICIENT_DATA — {len(hist['comparable'])} comparable records, "
                 f"need {MIN_HISTORY_FOR_TREND}. Run with --history again later.")
    elif not hist["clock_ok"]:
        L.append("  a record with an older timestamp was appended after a newer one — no trend reported")
    else:
        moved = [f for f in findings if f["id"].startswith("trend-")]
        L.append("  no source crossed the movement threshold" if not moved else
                 "\n".join(f"  {f['headline']}: {f['evidence']}" for f in moved))
    L.append("")
    L.append("population")
    L.append("  runtimes  : " + (", ".join(f"{k} ×{v}" for k, v in pop["runtimes"].most_common(4)) or "unknown"))
    L.append("  models    : " + (", ".join(f"{k} ×{v}" for k, v in pop["models"].most_common(4)) or "unknown"))
    L.append(f"  segmentation: {pop['segmentation']}")
    if pop["host_shift"]:
        a, b, mv = pop["host_shift"]
        L.append(f"  HOST_BEHAVIOR_SHIFT — runtime {','.join(a)} → {','.join(b)} with a {mv:.1f} pp move; "
                 "these records are not one population")
    L.append("")
    cands = [f for f in findings if f["state"] == "CANDIDATE"]
    obs = [f for f in findings if f["state"] == "OBSERVED"]
    L.append("candidates")
    if cands:
        for i, f in enumerate(cands, 1):
            L.append(f"  {i}. [{f['state']}] {f['id']} — {f['headline']}")
            L.append(f"       evidence: {f['evidence']}")
            L.append(f"       next    : {f['benchmark_required']}")
    else:
        L.append("  NO_ACTION — nothing crossed its pre-set threshold. This is a result, not a failure.")
    if obs:
        L.append("  observed, not actionable yet:")
        for f in obs:
            L.append(f"       [{f['state']}] {f['id']} — {f['headline']}")
            L.append(f"            {f['evidence']}")
    L.append("")
    L.append("policy mutation: NONE — this tool never edits skills, hooks or configuration.")
    return "\n".join(L)


def emit_candidates(findings, outdir):
    written = []
    for f in findings:
        if f["state"] != "CANDIDATE":
            continue
        d = os.path.join(outdir, f["id"])
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "HYPOTHESIS.md")
        body = f"""# Candidate: {f['id']}

state: {f['state']} (see experiments/candidates/README.md for the lifecycle)
date: {f['date']}

## Observation

{f['headline']} — {f['evidence']}

## Hypothesis

{f['hypothesis'] or '(none — this is an observation, not yet a hypothesis)'}

## Incumbent

SameWrite as released, unchanged.

## Candidate

To be written by a human or an authorised builder. This file is evidence and a specification;
nothing here changes runtime behaviour.

## Primary metric

{f['source_metric']} — reported with correctness and total task cost, never alone.

## Correctness gate

Correctness non-inferior to the incumbent on the same fixtures; safety-sensitive fixtures
(security, destructive) non-inferior.

## Instruction budget

always-on bytes delta: {f['always_on_bytes_delta']:+d}. A candidate that adds always-on text must
show `added_bytes × expected_turns` is smaller than the measured saving, and must name a rule it
replaces or compresses.

## Risk

{f['risk'] or 'unstated'}

## Affected layer

{f['affected_layer'] or 'unstated'}

## Benchmark required

{f['benchmark_required'] or 'development experiment + held-out confirmation'}

## Promotion criterion

CORRECTNESS_NON_INFERIOR and SAFETY_NON_INFERIOR and TOTAL_COST_IMPROVED and VERIFIER_SELFTEST
and HELD_OUT_CONFIRMATION and NO_PRIVACY_REGRESSION and NO_COEXISTENCE_REGRESSION — all of them,
on fixtures that were not used to invent the rule.
"""
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
        written.append(p)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description="offline evidence review; no model, no network")
    ap.add_argument("--history", default=os.path.expanduser("~/logs/carry_history.jsonl"))
    ap.add_argument("--ledger", default=os.path.expanduser("~/logs/samewrite.jsonl"))
    ap.add_argument("--scan", nargs="*", default=None,
                    help="transcripts or profile directories for a live snapshot; omit for auto-discovery, "
                         "pass --scan with no value to skip the live scan entirely")
    ap.add_argument("--min-turns", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--emit-candidate", metavar="DIR", default=None)
    a = ap.parse_args(argv)

    recs, rejected, lines = load_history(a.history)
    keep, dropped = comparable(recs)
    hist = {"total": len(recs), "comparable": keep, "dropped": dropped, "rejected": rejected,
            "lines": lines, "clock_ok": clock_ok(keep)}
    ledger = load_ledger(a.ledger)

    live = cold = None
    paths = []
    if a.scan is None or a.scan:
        try:
            import profiles
            paths, _roots = profiles.resolve(a.scan or [])      # same discovery every tool uses
        except Exception:
            paths = sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")))
    if paths:
        live = carry.accumulate(paths, min_turns=a.min_turns)
        try:
            listing, uses, sess = skills_tool.scan(paths)
            if listing:
                ent = skills_tool.parse_listing(listing)
                rows = skills_tool.tally(ent, uses, sess)
                cold_rows = [r for r in rows if r[2] == 0]
                cold = {"entries": len(rows), "cold": len(cold_rows),
                        "total_bytes": sum(r[1] for r in rows),
                        "cold_bytes": sum(r[1] for r in cold_rows)}
        except Exception:
            cold = None

    pop = population(keep, live)
    findings = analyse(live, hist, ledger, cold)
    sources = {"history": a.history if os.path.exists(a.history) else "",
               "ledger": a.ledger if ledger else ""}

    written = emit_candidates(findings, a.emit_candidate) if a.emit_candidate else []

    if a.json:
        print(json.dumps({
            "schema_version": carry.HISTORY_SCHEMA, "samewrite_version": carry.samewrite_version(),
            "generated": int(time.time()),
            "history": {"records": len(recs), "comparable": len(keep),
                        "rejected": dict(rejected), "clock_ok": hist["clock_ok"]},
            "ledger": ledger,
            "live": ({"sessions": live["sessions"], "turns": live["turns"],
                      "carry_shares": {k: round(100.0 * v / (sum(live["carry"].values()) or 1), 2)
                                       for k, v in live["carry"].most_common()}} if live else None),
            "listing": cold,
            "population": {"runtimes": dict(pop["runtimes"]), "models": dict(pop["models"]),
                           "segmentation": pop["segmentation"],
                           "host_behavior_shift": bool(pop["host_shift"])},
            "findings": findings,
            "result": "CANDIDATE" if any(f["state"] == "CANDIDATE" for f in findings) else "NO_ACTION",
            "candidate_files": written,
            "policy_mutation": "NONE",
        }, indent=2))
    else:
        print(render(live, hist, ledger, cold, pop, findings, sources))
        for p in written:
            print(f"  candidate written: {os.path.relpath(p, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
