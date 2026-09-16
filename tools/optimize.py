#!/usr/bin/env python3
"""Offline optimizer: read the aggregate evidence SameWrite already keeps, say where cost is
concentrated, what moved, and whether any of it is strong enough to justify an experiment.

    python3 tools/optimize.py                                   # this machine, default scope
    python3 tools/optimize.py --scope-id builder-01 --json
    python3 tools/optimize.py --emit-candidate ~/.local/state/samewrite/candidates

It calls no model, opens no socket, and writes nothing into any model's context. It reuses
`tools/carry.py` (live scan, history schema, trend) and the guard ledger — there is no second
telemetry channel. It never edits `skills/`, `hooks/` or any policy file, and it holds no Git or
GitHub authority: its output is a report and, on request, a candidate specification for a human.

Multi-agent safety (many agents, long-running, parallel sessions, several profiles):

  * every record belongs to a **scope**; records from different scopes are never merged, and a
    finding from one scope is labelled SCOPE_LOCAL rather than stated about everyone;
  * evidence carries its own **quality** — a sweep that hit unreadable files, oversized lines or
    a file cap is PARTIAL, and a candidate is not emitted from PARTIAL evidence unless the caller
    says that bounded corpus is the target;
  * identity is an opaque **run_id**, so two agents that happen to produce identical metrics are
    two observations, and a retried write is one;
  * candidates are **deterministic and deduplicated**, so a scheduler calling this every cycle
    produces no proposal spam.

THRESHOLDS ARE FIXED BELOW, BEFORE ANY REAL OUTCOME WAS READ, and carry a version of their own.
A finding that does not clear its threshold is reported as insufficient evidence, and NO_ACTION is
a successful run: the optimizer exists to refuse an optimization the data cannot support.
"""
import argparse, collections, hashlib, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import carry  # noqa: E402  (live scan, trend, history schema — reused, not duplicated)
import skills as skills_tool  # noqa: E402  (listing usage — reused)

OPTIMIZER_VERSION = "1.0"
OUTPUT_SCHEMA_VERSION = 1        # shape of --json; bump when a field's meaning changes
THRESHOLD_SCHEMA_VERSION = 1     # bump when any threshold below changes, with a reason and a test

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
MATERIAL_CHANGE_PP = 5.0     # evidence must move this far before a candidate is a NEW candidate

SCHEMA_SUPPORTED = (0, 1, 2)  # 0 = pre-1.2, 1 = + population identity, 2 = + run/scope/quality
STATES = ("OBSERVED", "HYPOTHESIS", "CANDIDATE", "EXPERIMENTAL", "PROVEN", "REJECTED")

# machine-readable outcome. The CLI exits 0 for every VALID run by default (a scheduler must not
# treat "nothing to do" as breakage); --strict-exit maps the status to the exit code instead.
# ---------------------------------------------------------------- evidence quality
# Ordered worst-last. A finding may be promoted to CANDIDATE only from COMPLETE evidence, or from
# PARTIAL evidence the caller explicitly accepted. Everything below PARTIAL is refused outright:
# --accept-partial says "this bounded population is the one I meant", which is a statement nobody
# can make about evidence that is corrupt, empty, or of unestablished provenance.
QUALITY_RANK = {"COMPLETE": 0, "PARTIAL": 1, "EMPTY": 2, "UNKNOWN": 3, "INVALID": 4}


SCHEMA_WITH_QUALITY = 2          # the first history schema that records how a sweep was taken
# What a sweep reports about its own acquisition. Schema 2 has carried all three since 1.2.0, so a
# schema-2 record that omits them is not an old record — it is a record that cannot show its work.
ACQUISITION_COUNTERS = ("unreadable", "oversize", "skipped_by_limit")
# Added in 1.3.1. Absence means "this sweep did not report it", never "there were none".
OPTIONAL_COUNTERS = ("malformed_lines",)


def derive_quality(rec):
    """What a record's OWN fields prove, ignoring what it claims.

    This mirrors the producer's rule in carry.accumulate() — the one place that actually knows how
    a sweep went — so the consumer can check a claim instead of believing it. A record may say
    COMPLETE while its counters record five unreadable files and a file cap; that is not a complete
    sweep, it is a claim about one. Claims are cheap; counters are evidence.
    """
    nums = {}
    for k in ACQUISITION_COUNTERS + OPTIONAL_COUNTERS + ("sessions", "turns", "scanned",
                                                         "carry_bytes"):
        if k not in rec:
            continue
        v = rec[k]
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            return "INVALID"          # a count that is not a count: the record is not trustworthy
        nums[k] = v
    if nums.get("sessions", 1) == 0:
        # the producer's own terms: a sweep that looked and found nothing usable is INVALID; one
        # that had nothing to look at is EMPTY
        return "INVALID" if nums.get("scanned", 0) > 0 else "EMPTY"
    if any(nums.get(k, 0) > 0 for k in ACQUISITION_COUNTERS + OPTIONAL_COUNTERS):
        return "PARTIAL"
    if not all(k in nums for k in ACQUISITION_COUNTERS):
        return "UNKNOWN"              # claims a completeness it cannot show
    return "COMPLETE"


def quality_of(rec):
    """Evidence quality of one history record. UNKNOWN unless the record can actually attest it.

    Two ways a record fails to attest:

      * the value is missing or unrecognised;
      * the record declares a schema older than the field itself. Schema 0/1 predates
        `evidence_quality`, so a schema-1 record carrying COMPLETE is asserting something its own
        writer could not have known. That is not provenance, it is a claim — from a hand-edited
        file or a migration that back-filled a default — and trusting it would reopen the hole this
        release closes through a side door.

    Either way the record stays readable and stays visible in reports. It simply cannot carry a
    promotion. Reading "not recorded" as "fine" is how a truncated log becomes a pass.
    """
    try:
        schema = int(rec.get("schema_version") or 0)
    except (TypeError, ValueError):
        schema = 0
    if schema < SCHEMA_WITH_QUALITY:
        return "UNKNOWN"
    q = rec.get("evidence_quality")
    claimed = q if isinstance(q, str) and q in QUALITY_RANK else "UNKNOWN"
    # The worst of the claim and the proof. A record may only ever describe itself as no better
    # than its own fields show — quality moves one way.
    return worst_quality([claimed, derive_quality(rec)])


def worst_quality(qualities):
    """The worst quality in the set. Not a vote: one partial observation among nine complete ones
    still means part of the evidence was never swept, and nine neighbours cannot launder it.
    An empty set is COMPLETE — a finding that draws on no sampled evidence is not degraded by
    sampling that had nothing to do with it."""
    worst = "COMPLETE"
    for q in qualities:
        if QUALITY_RANK.get(q, QUALITY_RANK["UNKNOWN"]) > QUALITY_RANK[worst]:
            worst = q if q in QUALITY_RANK else "UNKNOWN"
    return worst


def emittable(quality, accept_partial):
    """May a finding at this evidence quality become a CANDIDATE?"""
    return quality == "COMPLETE" or (quality == "PARTIAL" and bool(accept_partial))


def effective_quality(live, comparable_records):
    """ONE quality for the whole run, over the evidence actually ELIGIBLE to support a finding.

    Eligibility is not this function's judgement — `comparable()` already made it: same scope, same
    workload class, compatible corpus size, quality not INVALID/EMPTY. A partial record belonging
    to another agent's scope, or to another workload class, or dropped as non-comparable, is not
    evidence for this run and must not block it. That half matters as much as the fail-closed half:
    a gate that blocks on evidence a finding never used is not correct, it is merely stuck.
    """
    qs = [quality_of(r) for r in (comparable_records or [])]
    if live:
        qs.append(live.get("quality") or "UNKNOWN")
    return worst_quality(qs)


STATUS = {"NO_ACTION": 0, "CANDIDATE": 10, "INSUFFICIENT_DATA": 20, "HOST_BEHAVIOR_SHIFT": 30,
          "PARTIAL_EVIDENCE": 40, "ALREADY_RUNNING": 41, "INTERNAL_ERROR": 50}

SOURCE_HINT = {
    "Bash": ("bash-output-shaping", "ask Bash for the answer, not the log: failures-only, bounded "
             "output, counts instead of listings", "skill body (no always-on bytes)"),
    "Read": ("read-range-discipline", "read a range or a symbol, not a whole file",
             "skill body (no always-on bytes)"),
    "prose": ("output-economy", "shorter answers where nothing is lost", "skill body (no always-on bytes)"),
    "Write/Edit": ("edit-discipline", "anchored Edit under ~25% changed; never rewrite what is identical",
                   "skill body (no always-on bytes)"),
}
# Invariants a candidate MUST carry, because the cheap version of it is dangerous.
EVIDENCE_INVARIANT = (
    "Never truncate the only copy of evidence. Raw output stays outside the model's context (host "
    "log, file, or the caller's own spool); the model receives a bounded digest; full detail stays "
    "retrievable on failure or on explicit request. For security, governance, build validation, "
    "destructive operations and any failure path, the raw record must survive. "
    "ONE CARVE-OUT, and it is not optional: secret material is never the evidence. A credential, "
    "key or token appearing in output is redacted at capture and never written verbatim into a "
    "retained artifact — preserving it is a leak wearing the word 'evidence'. Keep the finding, "
    "the location and the fact of exposure; never the value.")
SCOPE_INVARIANT = (
    "Scope-local evidence. A listing entry cold in one role can be essential to another: this "
    "candidate is about reducing exposure IN THIS SCOPE, after proving no other role needs it. It "
    "is never an instruction to uninstall anything globally, and nothing is removed automatically.")


# ---------------------------------------------------------------- privacy-safe diagnostics
def safe(path):
    """A diagnostic must not leak where the machine keeps things. Name only, never the path."""
    try:
        return os.path.basename(str(path)) or "(unnamed)"
    except Exception:
        return "(unnamed)"


def safe_err(exc):
    """Exception text can carry an absolute path (OSError.filename always does). Report the class
    and the errno, never the message."""
    en = getattr(exc, "errno", None)
    return f"{type(exc).__name__}" + (f" (errno {en})" if en else "")


# ---------------------------------------------------------------- history: load and validate
def valid_record(o):
    """-> (ok, reason). Malformed input must not poison a trend; it must be counted and dropped."""
    if not isinstance(o, dict):
        return False, "not an object"
    if o.get("record_type") not in (None, "carry_run"):
        return False, "unknown record_type"
    sv = o.get("schema_version", 0)
    if not isinstance(sv, int) or isinstance(sv, bool) or sv not in SCHEMA_SUPPORTED:
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
    q = o.get("evidence_quality")
    if q is not None and q not in ("COMPLETE", "PARTIAL", "INVALID", "EMPTY"):
        return False, "unknown evidence_quality"
    return True, ""


def scope_of(r):
    return str(r.get("scope_id") or "default")


def load_history(path):
    """-> (records, rejected counter, lines). Deduplication is by run_id ONLY: two agents can
    legitimately produce the same timestamp, turn count and shares, and discarding one of them
    would undercount the population. A record without a run_id (schema 0/1) cannot be deduplicated
    and is kept as it is."""
    recs, rejected = [], collections.Counter()
    if not path or not os.path.exists(path):
        return recs, rejected, 0
    lines = 0
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError as e:
        rejected[f"history unreadable: {safe_err(e)}"] += 1
        return recs, rejected, 0
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            lines += 1
            if len(line) > carry.MAX_RECORD:
                rejected["record above the size cap"] += 1
                continue
            try:
                o = json.loads(line)
            except Exception:
                rejected["unparseable line"] += 1
                continue
            ok, why = valid_record(o)
            (recs.append(o) if ok else rejected.__setitem__(why, rejected[why] + 1))
    seen, uniq = {}, []
    for r in recs:
        rid = r.get("run_id")
        if isinstance(rid, str) and rid:
            if rid in seen:
                rejected["duplicate run_id (retry)"] += 1
                # The retry is dropped as an observation, but not as PROVENANCE. One run_id that
                # says COMPLETE once and PARTIAL once cannot be resolved in favour of the better
                # claim: the sweep that reported less is part of what this id actually saw. Keep
                # the worse quality on the record that survives.
                kept = seen[rid]
                worse = worst_quality([quality_of(kept), quality_of(r)])
                if worse != quality_of(kept):
                    kept["evidence_quality"] = worse
                    kept["schema_version"] = max(int(kept.get("schema_version") or 0),
                                                 SCHEMA_WITH_QUALITY)
                continue
            seen[rid] = r
        uniq.append(r)
    return uniq, rejected, lines


def by_scope(recs):
    out = collections.defaultdict(list)
    for r in recs:
        out[scope_of(r)].append(r)
    return dict(out)


def comparable(recs):
    """Records that may be compared with the newest one: same scope, same workload class,
    compatible corpus size, usable evidence quality."""
    if not recs:
        return [], []
    # Eligibility FIRST, anchor second. Choosing the newest record from the whole file and then
    # discarding it as unusable let a record that never qualified define the workload class and
    # corpus size every other record was measured against — one INVALID arrival could strand a
    # complete population. And the test is the DERIVED quality, not the claimed one: the same rule
    # the rest of this module uses, or the filter and the gate disagree about what a record is.
    keep, dropped = [], []
    eligible = []
    for r in recs:
        q = quality_of(r)
        if q in ("INVALID", "EMPTY"):
            dropped.append((r, "evidence quality " + q))
        else:
            eligible.append(r)
    if not eligible:
        return [], dropped
    newest = max(eligible, key=lambda r: r.get("ts") or 0)
    n_turn = newest.get("turns") or 0
    n_scope = scope_of(newest)
    n_work = str(newest.get("workload_class") or "")
    for r in eligible:
        if scope_of(r) != n_scope:
            dropped.append((r, f"scope {scope_of(r)!r} vs {n_scope!r}"))
            continue
        if str(r.get("workload_class") or "") != n_work:
            dropped.append((r, f"workload class {str(r.get('workload_class') or '')!r} vs {n_work!r} "
                               "— WORKLOAD_SHIFT, not a trend"))
            continue
        t = r.get("turns") or 0
        if n_turn and t and max(n_turn, t) / min(n_turn, t) > CORPUS_TURN_RATIO_MAX:
            dropped.append((r, f"corpus {t:,} turns vs {n_turn:,}"))
            continue
        keep.append(r)
    return keep, dropped


def time_order(recs):
    """-> 'ok' | 'reversed' | 'ambiguous'. A 24x7 system sees clock skew; a trend must not invent
    a direction from timestamps that cannot order the records."""
    ts = [r.get("ts") or 0 for r in recs]
    if len(ts) < 2:
        return "ok"
    if len(set(ts)) == 1:
        return "ambiguous"
    if ts != sorted(ts):
        return "reversed"
    return "ok"


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
    checked = denied = rejected = 0
    if not path or not os.path.exists(path):
        return None
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with fh:
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
def digest(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def bucket_of(value, width=MATERIAL_CHANGE_PP):
    return int(value // width)


def finding(cid, state, headline, evidence, scope="default", bucket=0, hypothesis="", metric="",
            effect="", risk="", layer="", always_on_bytes=0, benchmark="", invariants=(),
            evidence_runs=(), global_claim=False, evidence_source="sampled",
            evidence_quality="COMPLETE", partial_accepted=False):
    """`bucket` is the coarse evidence level this finding was produced at: two runs whose evidence
    lands in the same bucket are the SAME candidate, which is what stops a 24x7 scheduler from
    writing a new proposal every cycle."""
    cand_id = f"{cid}-{scope}-{digest(cid, scope, THRESHOLD_SCHEMA_VERSION, bucket)[:8]}"
    return dict(id=cid, candidate_id=cand_id, state=state, headline=headline, evidence=evidence,
                scope_id=scope, scope_claim="GLOBAL" if global_claim else "SCOPE_LOCAL",
                evidence_bucket=bucket, hypothesis=hypothesis, source_metric=metric,
                expected_effect=effect, risk=risk, affected_layer=layer,
                always_on_bytes_delta=always_on_bytes, benchmark_required=benchmark,
                invariants=list(invariants), evidence_run_ids=list(evidence_runs)[:20],
                # Provenance travels WITH the finding, from the evidence that produced it. The
                # previous version stamped it afterwards by list position, and a finding appended
                # after that boundary silently inherited the wrong source.
                evidence_source=evidence_source,
                effective_evidence_quality=evidence_quality,
                partial_evidence_accepted=bool(partial_accepted),
                optimizer_version=OPTIMIZER_VERSION, threshold_schema_version=THRESHOLD_SCHEMA_VERSION,
                samewrite_version=carry.samewrite_version(),
                date=time.strftime("%Y-%m-%d", time.gmtime()))


def analyse(live, hist, ledger, cold, scope="default", accept_partial=False, effective=None,
            population_ok=True):
    out = []
    # The quality that governs promotion is the worst across the live sweep AND the history records
    # that actually feed these findings — not the live sweep alone. Reading only the live sweep is
    # how a bounded history became indistinguishable from a complete one (SW-1303).
    quality = effective if effective is not None else effective_quality(live, hist.get("comparable"))
    # ONE promotion gate for sampled findings. A population the analyser has declared not to be
    # one world is not evidence you may promote from, any more than a bounded sweep is: the run
    # said "these records do not describe the same thing", and a candidate says "they do".
    usable = emittable(quality, accept_partial) and population_ok
    accepted = bool(accept_partial and quality == "PARTIAL")

    def sampled(*a, **kw):
        """A finding measured from the swept corpus: it carries the run's evidence quality."""
        return finding(*a, evidence_source="sampled", evidence_quality=quality,
                       partial_accepted=accepted, **kw)

    def from_ledger(*a, **kw):
        """A finding counted from the hook ledger: writes actually denied, which no sweep bound can
        make partial. It is not degraded by sampling it never used."""
        return finding(*a, evidence_source="ledger", evidence_quality="COMPLETE",
                       partial_accepted=False, **kw)

    run_ids = [r.get("run_id") for r in hist.get("comparable", []) if r.get("run_id")]

    # 1. concentration — only sayable over a corpus, never over one session, and never from a
    #    corpus that could not be swept completely
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
                  f"{live['turns']:,} turns in scope {scope!r} (evidence {quality})")
            if enough and usable:
                out.append(sampled(cid, "CANDIDATE", f"{src} dominates carry", ev, scope=scope,
                                   bucket=bucket_of(share),
                                   hypothesis=f"{fix} lowers total task cost without lowering correctness",
                                   metric=f"carry share of {src}", effect="unknown until measured",
                                   risk="a rule that shortens evidence can raise retries",
                                   layer=layer, always_on_bytes=0, evidence_runs=run_ids,
                                   invariants=(EVIDENCE_INVARIANT, SCOPE_INVARIANT),
                                   benchmark="paired fixtures, correctness gate first, then total cost; one "
                                             "fixture must be an audit workload whose verbose output IS the "
                                             "evidence"))
            else:
                why = ("below the %d-session / %d-turn floor" % (MIN_SESSIONS, MIN_TURNS)) if not enough \
                    else f"evidence is {quality}, not a population"
                out.append(sampled(cid, "OBSERVED", f"{src} dominates carry", ev + " — " + why,
                                   scope=scope, bucket=bucket_of(share), metric=f"carry share of {src}",
                                   invariants=(EVIDENCE_INVARIANT, SCOPE_INVARIANT)))
    # 2. movement — needs a comparable history, in one scope, with usable time order
    if hist["comparable"] and hist.get("time_order", "ok") == "ok":
        keys = set()
        for r in hist["comparable"]:
            keys.update(r.get("shares", {}))
        moves = []
        for k in sorted(keys):
            t = carry.trend(hist["comparable"], k, min_n=MIN_HISTORY_FOR_TREND)
            if t and abs(t["slope"] * 30.0) >= TREND_MIN_SLOPE:
                moves.append((k, t["slope"] * 30.0, t))
        reported = []
        for k, per_month, t in sorted(moves, key=lambda x: -abs(x[1])):
            # A share vector sums to 100, so one source rising IS another falling. Reporting both
            # is the SAME movement twice: it doubles every proposal for zero information, and a
            # reader who sees two files assumes two problems. Keep the larger mover, name the
            # complement inside its evidence.
            mirror = next((rk for rk, rp in reported
                           if abs(rp + per_month) <= max(0.01 * abs(rp), 0.05)), None)
            if mirror:
                for f in out:
                    if f["id"] == "trend-" + re.sub(r"[^a-z0-9]+", "-", mirror.lower()).strip("-"):
                        f["evidence"] += f"; {k} moves by the same amount in the other direction, " \
                                         f"which is the same movement, not a second one"
                continue
            reported.append((k, per_month))
            if True:
                cid = "trend-" + re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")
                spike = (" — but the last value sits z=%+.1f from its own history, so this slope "
                         "may be one spike rather than a shift" % t["z"]) if abs(t["z"]) >= TREND_MIN_Z else ""
                # The trend reads the comparable history directly, so it is exactly the finding
                # SW-1303 let through: before this gate it emitted a CANDIDATE with no reference to
                # evidence quality at all.
                out.append(sampled(cid, "CANDIDATE" if usable else "OBSERVED",
                                   f"{k} share is moving",
                                   f"{per_month:+.1f} pp/month over {t['n']} records in scope {scope!r}, "
                                   f"last value z={t['z']:+.1f}{spike}"
                                   + ("" if usable else
                                      (f" — evidence is {quality}, not a population" if population_ok
                                       else " — the runtime mix shifted, so these records do not "
                                            "describe one population")),
                                   scope=scope,
                                   # DIRECTION, not magnitude. A fitted slope decays as its window
                                   # grows even when the world stopped moving, so bucketing the
                                   # magnitude mints a fresh proposal every time the estimator
                                   # settles. One sustained movement is one proposal; a REVERSAL
                                   # is a new one, which is exactly when a human should look again.
                                   bucket=1 if per_month > 0 else -1,
                                   hypothesis=f"the change in {k} is a shift, not a spike, and has a cause worth naming",
                                   metric=f"slope of {k} share", effect="unknown until measured",
                                   risk="a trend can come from the workload, not from SameWrite",
                                   layer="investigation only", always_on_bytes=0, evidence_runs=run_ids,
                                   invariants=(SCOPE_INVARIANT,),
                                   benchmark="identify the cause before proposing a rule"))
    # 3. the guard: does it still pay for itself? (rule retirement is a first-class outcome)
    if ledger and ledger["writes"]:
        if ledger["writes"] >= LEDGER_MIN_WRITES:
            if ledger["rate"] >= LEDGER_MIN_NOOP_RATE:
                out.append(from_ledger("noop-guard-retain", "OBSERVED", "the no-op guard is still paying",
                                   f"{ledger['prevented']} of {ledger['writes']} writes prevented "
                                   f"({ledger['rate']:.1f}% >= {LEDGER_MIN_NOOP_RATE}%)",
                                   scope=scope, bucket=bucket_of(ledger["rate"]), metric="ledger deny rate"))
            else:
                out.append(from_ledger("noop-guard-retire", "CANDIDATE", "the no-op guard may have stopped paying",
                                   f"{ledger['prevented']} of {ledger['writes']} writes prevented "
                                   f"({ledger['rate']:.1f}% < {LEDGER_MIN_NOOP_RATE}%)",
                                   scope=scope, bucket=bucket_of(ledger["rate"]),
                                   hypothesis="the hook's cost is no longer covered by what it prevents; removing it "
                                              "is the change to test",
                                   metric="ledger deny rate", effect="one fewer PreToolUse hook",
                                   risk="a low field rate can be the read-then-write bypass, not absence of no-ops",
                                   layer="hook (removal)", always_on_bytes=0, evidence_runs=run_ids,
                                   invariants=(SCOPE_INVARIANT,),
                                   benchmark="re-measure on a fresh sample before removing"))
        else:
            out.append(from_ledger("noop-guard", "OBSERVED", "the guard's field sample is too small to judge",
                               f"{ledger['writes']} writes recorded, need {LEDGER_MIN_WRITES}",
                               scope=scope, metric="ledger deny rate"))
    # 4. the listing this scope pays for on every turn — never a global prune
    if cold:
        share = 100.0 * cold["cold_bytes"] / (cold["total_bytes"] or 1)
        ev = (f"in scope {scope!r}: {cold['cold']}/{cold['entries']} entries never invoked, "
              f"{cold['cold_bytes']:,} of {cold['total_bytes']:,} listing bytes ({share:.1f}%), "
              f"evidence {quality}")
        if share >= COLD_LISTING_MIN_SHARE and cold["cold_bytes"] >= COLD_LISTING_MIN_BYTES and usable:
            out.append(sampled("listing-prune", "CANDIDATE",
                               "most of the skill listing is never invoked IN THIS SCOPE", ev, scope=scope,
                               bucket=bucket_of(share),
                               hypothesis="reducing listing exposure in this scope removes always-on carry with no "
                                          "loss — after proving no other role needs those entries",
                               metric="cold share of the skill listing",
                               effect=f"~{cold['cold_bytes']:,} bytes per turn in this scope",
                               risk="a description can route without ever being loaded, and an entry cold here can "
                                    "be essential to another role — this is an upper bound on waste, in one scope",
                               layer="scope configuration, not SameWrite text", always_on_bytes=-cold["cold_bytes"],
                               evidence_runs=run_ids, invariants=(SCOPE_INVARIANT,),
                               benchmark="prove the entry is cold in every role that shares this configuration, then "
                                         "reduce exposure for THIS scope only and measure both roles"))
        else:
            out.append(sampled("listing-prune", "OBSERVED",
                               "skill listing is mostly used, or evidence is not a population", ev, scope=scope,
                               bucket=bucket_of(share), metric="cold share of the skill listing",
                               invariants=(SCOPE_INVARIANT,)))
    return out


def overall_status(findings, hist, live, pop, accept_partial, effective=None):
    if pop.get("host_shift"):
        # Reported first, and analyse() has already refused to promote anything sampled, so this
        # status can never coexist with a candidate file. A status that says "refused" while a
        # proposal sits on disk is a contract no automation can act on.
        return "HOST_BEHAVIOR_SHIFT"
    q = effective if effective is not None else effective_quality(live, hist.get("comparable"))
    # A status that says PARTIAL_EVIDENCE while candidate files sit on disk is a contradiction a
    # machine cannot resolve. Findings that draw on no sampled evidence — the hook ledger counts
    # writes that were actually denied, which no sweep bound can make partial — are still
    # promotable, so if anything WAS produced the status says so and the refused sampled evidence
    # travels in effective_evidence_quality instead of being smuggled into the status word.
    if any(f["state"] == "CANDIDATE" for f in findings):
        return "CANDIDATE"
    if not emittable(q, accept_partial):
        # One status for "this evidence may not carry a promotion"; the precise reason travels in
        # effective_evidence_quality so automation need not parse prose and the CLI's documented
        # status vocabulary and exit codes stay exactly as they were.
        return "PARTIAL_EVIDENCE"
    if not live and len(hist.get("comparable", [])) < MIN_HISTORY_FOR_TREND:
        return "INSUFFICIENT_DATA"
    return "NO_ACTION"


# ---------------------------------------------------------------- candidate emission
def spec_text(f):
    inv = "\n".join(f"- {x}" for x in f["invariants"]) or "- (none recorded)"
    runs = ", ".join(f["evidence_run_ids"]) or "(records without run ids)"
    return f"""# Candidate: {f['id']}

candidate_id: {f['candidate_id']}
state: {f['state']} (lifecycle: experiments/candidates/README.md)
scope_id: {f['scope_id']}
scope_claim: {f['scope_claim']}
optimizer_version: {f['optimizer_version']}
threshold_schema_version: {f['threshold_schema_version']}
samewrite_version: {f['samewrite_version']}
evidence_bucket: {f['evidence_bucket']}
effective_evidence_quality: {f.get('effective_evidence_quality', 'UNKNOWN')}
partial_evidence_accepted: {str(bool(f.get('partial_evidence_accepted'))).lower()}
evidence_run_ids: {runs}
created_at: {f['date']}

## Observation

{f['headline']} — {f['evidence']}

## Hypothesis

{f['hypothesis'] or '(none — this is an observation, not yet a hypothesis)'}

## Invariants this candidate must not break

{inv}

## Incumbent

SameWrite as released, unchanged.

## Candidate

To be written by a human or a separately authorised builder. This file is evidence and a
specification; nothing here changes runtime behaviour, and the optimizer that wrote it holds no
implementation, Git or promotion authority.

## Primary metric

{f['source_metric']} — reported with correctness and total task cost, never alone.

## Correctness gate

Correctness non-inferior to the incumbent on the same fixtures; safety-sensitive fixtures
(security, destructive, audit-evidence) non-inferior. Where the change touches configuration shared
by several roles, every other role must be measured unaffected.

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

CORRECTNESS_NON_INFERIOR and SAFETY_NON_INFERIOR and TOTAL_COST_IMPROVED and VERIFIER_SELFTEST and
HELD_OUT_CONFIRMATION and NO_PRIVACY_REGRESSION and NO_COEXISTENCE_REGRESSION — all of them, on
fixtures that were not used to invent the rule, and none of it applied automatically.
"""


# What an existing candidate artifact turned out to be.
ARTIFACT_CURRENT = "PROVEN_CURRENT"
ARTIFACT_PRE_131 = "PRE_1_3_1_REVIEW_REQUIRED"
ARTIFACT_UNKNOWN = "UNREADABLE_OR_UNVERIFIABLE"


def artifact_metadata(path):
    """-> (state, fields). Read a candidate's metadata HEADER, not the whole file.

    The first version asked whether the string "effective_evidence_quality:" appeared anywhere in
    the file. A sentence mentioning the field satisfied that; an unreadable file quietly counted as
    current; and a file with invalid UTF-8 raised straight past the handler and killed the run.
    Provenance is a structural property, so it is read structurally: `key: value` lines in the
    header block, stopping at the first blank line or section heading, with a bound so a large or
    hostile file cannot be walked forever.

    Anything that cannot be read, decoded or parsed is UNVERIFIABLE. That is the fail-closed
    direction: an artifact we cannot characterise is never a trusted one.
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read(64 * 1024)
    except OSError:
        return ARTIFACT_UNKNOWN, {}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ARTIFACT_UNKNOWN, {}
    fields = {}
    for line in text.splitlines()[:200]:
        if not line.strip():
            if fields:
                break                       # the header ends at the first blank line after it
            continue
        if line.startswith("#"):
            if fields:
                break                       # ...or at the first section heading after it
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip() != key or not key:
            continue                        # indented or prose-wrapped: not a header field
        fields[key] = value.strip()
    if fields.get("effective_evidence_quality", "") in QUALITY_RANK:
        return ARTIFACT_CURRENT, fields
    return ARTIFACT_PRE_131, fields


def emit_candidates(findings, outdir):
    """Atomic, deduplicated, and never inside a governed tree by default.

    -> (written, existing, failed, review_required, unverifiable). A candidate whose id already
    exists is NOT rewritten: the evidence bucket is part of the id, so a file reappears only when
    the evidence actually moved."""
    written, existing, failed = [], [], []
    review_required, unverifiable = [], []
    for f in findings:
        if f["state"] != "CANDIDATE":
            continue
        d = os.path.join(outdir, f["candidate_id"])
        p = os.path.join(d, "HYPOTHESIS.md")
        if os.path.exists(p):
            # Never rewritten, never deleted — only classified. An artifact from before 1.3.1
            # carries no evidence provenance and may be residue of the defect this release fixes;
            # one that cannot be read at all is not evidence of anything.
            state, _fields = artifact_metadata(p)
            {ARTIFACT_CURRENT: existing,
             ARTIFACT_PRE_131: review_required,
             ARTIFACT_UNKNOWN: unverifiable}[state].append(f["candidate_id"])
            continue
        try:
            os.makedirs(d, exist_ok=True)
            tmp = p + ".tmp-%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(spec_text(f))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, p)                 # a crash leaves the old file or the new one, never half
            written.append(f["candidate_id"])
        except OSError as e:
            failed.append((f["candidate_id"], safe_err(e)))
    return written, existing, failed, review_required, unverifiable


class Lock:
    """Non-blocking lock so two scheduler invocations cannot write candidates at the same time.
    Read-only analysis needs no lock and never blocks."""

    def __init__(self, path):
        self.path = path
        self.fd = None

    def __enter__(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(self.fd, str(os.getpid()).encode())
            return True
        except FileExistsError:
            return False
        except OSError:
            return True              # a lock we cannot take must not stop a read-only report

    def __exit__(self, *exc):
        if self.fd is not None:
            try:
                os.close(self.fd)
                os.unlink(self.path)
            except OSError:
                pass
        return False


# ---------------------------------------------------------------- rendering
def render(live, hist, ledger, cold, pop, findings, sources, status, scope, scopes_seen,
           effective=None, accept_partial=False):
    L = ["SameWrite Health — evidence-adaptive optimizer", ""]
    L.append(f"status    : {status}   scope: {scope}"
             + (f"   (history also holds: {', '.join(sorted(s for s in scopes_seen if s != scope))})"
                if len(scopes_seen) > 1 else ""))
    if effective is not None:
        L.append(f"evidence  : {effective}"
                 + ("   (accepted with --accept-partial)" if accept_partial and effective == "PARTIAL"
                    else ""))
        if not emittable(effective, accept_partial):
            # Refusing without saying why teaches the reader to ignore the refusal.
            why = {"PARTIAL": "part of the corpus was never swept — a file cap, an unreadable "
                              "transcript, or an oversize line",
                   "UNKNOWN": "a record does not record how its sweep was taken (schema 0/1), so "
                              "completeness cannot be established",
                   "INVALID": "a sweep ran but produced no usable session",
                   "EMPTY": "there was nothing to sweep"}.get(effective, "evidence is not a population")
            L.append(f"            no candidate may be promoted from this evidence: {why}.")
            if effective == "PARTIAL":
                L.append("            pass --accept-partial if this bounded corpus IS the population "
                         "you meant.")
    L.append("scope")
    L.append(f"  history   : {sources['history'] or '(none)'} — {hist['total']} records, "
             f"{hist['in_scope']} in this scope, {len(hist['comparable'])} comparable, "
             f"{sum(hist['rejected'].values())} rejected, time order {hist['time_order']}")
    for why, n in hist["rejected"].most_common():
        L.append(f"              rejected: {n} × {why}")
    for _, why in hist["dropped"][:3]:
        L.append(f"              not comparable: {why}")
    L.append(f"  ledger    : {sources['ledger'] or '(none)'} — "
             + (f"{ledger['writes']} writes, {ledger['prevented']} identical prevented" if ledger else "no records"))
    if live:
        L.append(f"  live scan : {live['sessions']} sessions / {live['turns']:,} turns "
                 f"({live['scanned']} transcripts, {live['short']} below the turn floor, "
                 f"{live.get('unreadable', 0)} unreadable, {live.get('oversize', 0)} oversized lines)")
        L.append(f"  evidence  : {live.get('quality', 'COMPLETE')}")
    L.append("")
    if live and live["sessions"]:
        C = sum(live["carry"].values()) or 1
        L.append("where cost is concentrated (carry = size × turns remaining)")
        for src, val in live["carry"].most_common(6):
            L.append(f"  {src:<34} {100.0 * val / C:5.1f}%")
        L.append("")
    L.append("movement")
    if hist["time_order"] != "ok":
        L.append(f"  TREND_AMBIGUOUS — records cannot be ordered in time ({hist['time_order']}); "
                 "no direction reported")
    elif len(hist["comparable"]) < MIN_HISTORY_FOR_TREND:
        L.append(f"  INSUFFICIENT_DATA — {len(hist['comparable'])} comparable records in this scope, "
                 f"need {MIN_HISTORY_FOR_TREND}. Run with --history again later.")
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
            L.append(f"  {i}. [{f['state']}] {f['candidate_id']} ({f['scope_claim']})")
            L.append(f"       {f['headline']}")
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
    L.append("policy mutation: NONE — this tool never edits skills, hooks or configuration, and holds "
             "no Git or GitHub authority.")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="offline evidence review; no model, no network")
    ap.add_argument("--history", default=os.path.expanduser("~/logs/carry_history.jsonl"))
    ap.add_argument("--ledger", default=os.path.expanduser("~/logs/samewrite.jsonl"))
    ap.add_argument("--scan", nargs="*", default=None,
                    help="transcripts or profile directories for a live snapshot; omit for auto-discovery, "
                         "pass --scan with no value to skip the live scan entirely")
    ap.add_argument("--scope-id", default=None,
                    help="analyse only this scope. Without it: the newest scope in the history; other scopes "
                         "are named but never merged into it.")
    ap.add_argument("--min-turns", type=int, default=50)
    ap.add_argument("--max-files", type=int, default=0,
                    help="bounded mode: scan at most N transcripts (evidence is marked PARTIAL)")
    ap.add_argument("--accept-partial", action="store_true",
                    help="treat a PARTIAL sweep as the intended bounded corpus, not as a broken population")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict-exit", action="store_true",
                    help="exit with the machine status code instead of 0 for a valid run")
    ap.add_argument("--emit-candidate", metavar="DIR", default=None,
                    help="write one specification per candidate. Point this at a state directory, not at a "
                         "governed repository: the optimizer has no authority to change code.")
    a = ap.parse_args(argv)

    recs, rejected, lines = load_history(a.history)
    scopes = by_scope(recs)
    scopes_seen = sorted(scopes) or ["default"]
    if a.scope_id:
        scope, scoped = a.scope_id, scopes.get(a.scope_id, [])
    elif recs:
        scope = scope_of(max(recs, key=lambda r: r.get("ts") or 0))
        scoped = scopes[scope]
    else:
        scope, scoped = "default", []
    keep, dropped = comparable(scoped)
    hist = {"total": len(recs), "in_scope": len(scoped), "comparable": keep, "dropped": dropped,
            "rejected": rejected, "lines": lines, "time_order": time_order(keep)}
    ledger = load_ledger(a.ledger)

    live = cold = None
    paths = []
    if a.scan is None or a.scan:
        try:
            import profiles
            paths, _roots = profiles.resolve(a.scan or [])      # same discovery every tool uses
        except Exception:
            paths = []
    if paths:
        live = carry.accumulate(paths, min_turns=a.min_turns, max_files=a.max_files)
        try:
            # The SAME bounded selection carry uses. Slicing discovery order here while
            # carry took the newest by mtime made the two halves of one run describe two
            # different corpora under --max-files.
            listing, uses, sess = skills_tool.scan(carry.bounded_paths(paths, a.max_files))
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
    # Computed ONCE and handed to every consumer: the report, the JSON, the candidate emitter and
    # the status. Three copies of this rule would be three chances for them to disagree.
    effective = effective_quality(live, hist.get("comparable"))
    findings = analyse(live, hist, ledger, cold, scope=scope, accept_partial=a.accept_partial,
                       effective=effective, population_ok=not pop.get("host_shift"))
    status = overall_status(findings, hist, live, pop, a.accept_partial, effective=effective)
    sources = {"history": safe(a.history) if os.path.exists(a.history) else "",
               "ledger": safe(a.ledger) if ledger else ""}

    written, existing, failed = [], [], []
    review_required, unverifiable = [], []
    if a.emit_candidate:
        with Lock(os.path.join(a.emit_candidate, ".optimize.lock")) as got:
            if not got:
                status = "ALREADY_RUNNING"
            else:
                (written, existing, failed,
                 review_required, unverifiable) = emit_candidates(findings, a.emit_candidate)

    if a.json:
        print(json.dumps({
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "optimizer_version": OPTIMIZER_VERSION,
            "threshold_schema_version": THRESHOLD_SCHEMA_VERSION,
            "samewrite_version": carry.samewrite_version(),
            "history_schema_supported": list(SCHEMA_SUPPORTED),
            "generated": int(time.time()),
            "status": status, "status_code": STATUS.get(status, STATUS["INTERNAL_ERROR"]),
            "scope": {"analysed": scope, "known": scopes_seen, "records_in_scope": len(scoped),
                      "comparable": len(keep)},
            # unchanged meaning: the quality of THIS run's live sweep alone
            "evidence_quality": (live or {}).get("quality", "NO_SCAN") if live else "NO_SCAN",
            # added in 1.3.1: the worst quality across the live sweep AND the comparable history,
            # i.e. the value that actually decides whether a finding may be promoted
            "effective_evidence_quality": effective,
            "partial_evidence_accepted": bool(a.accept_partial and effective == "PARTIAL"),
            "history": {"records": len(recs), "comparable": len(keep),
                        "rejected": dict(rejected), "time_order": hist["time_order"]},
            "ledger": ledger,
            "live": ({"sessions": live["sessions"], "turns": live["turns"], "scanned": live["scanned"],
                      "unreadable": live.get("unreadable", 0), "oversize": live.get("oversize", 0),
                      "skipped_by_limit": live.get("skipped_by_limit", 0),
                      "carry_shares": {k: round(100.0 * v / (sum(live["carry"].values()) or 1), 2)
                                       for k, v in live["carry"].most_common()}} if live else None),
            "listing": cold,
            "population": {"runtimes": dict(pop["runtimes"]), "models": dict(pop["models"]),
                           "segmentation": pop["segmentation"],
                           "host_behavior_shift": bool(pop["host_shift"])},
            "findings": findings,
            "candidate_ids": [f["candidate_id"] for f in findings if f["state"] == "CANDIDATE"],
            # candidates_existing keeps its original meaning: bare candidate ids, usable as
            # directory names and in set comparisons. The 1.3.1 review states travel in their own
            # additive fields rather than being encoded into the ids as prose — a consumer that
            # treated an id as an id would have broken exactly on the upgrade.
            "candidates_written": written, "candidates_existing": existing,
            "candidates_existing_review_required": review_required,
            "candidates_existing_unverifiable": unverifiable,
            "candidates_failed": [c for c, _ in failed],
            "policy_mutation": False,
        }, indent=2))
    else:
        print(render(live, hist, ledger, cold, pop, findings, sources, status, scope, scopes_seen,
                     effective=effective, accept_partial=a.accept_partial))
        for c in written:
            print(f"  candidate written: {c}")
        for c in existing:
            print(f"  EXISTING_CANDIDATE (no new action): {c}")
        for c in review_required:
            print(f"  EXISTING_CANDIDATE, pre-1.3.1 — carries no evidence provenance, re-review: {c}")
        for c in unverifiable:
            print(f"  EXISTING_CANDIDATE, UNVERIFIABLE — could not be read or decoded: {c}")
        for c, why in failed:
            print(f"  candidate could NOT be written: {c} — {why}")
    return STATUS.get(status, STATUS["INTERNAL_ERROR"]) if a.strict_exit else 0


if __name__ == "__main__":
    sys.exit(main())
