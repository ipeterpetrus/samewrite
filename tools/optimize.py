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
OUTPUT_SCHEMA_VERSION = 2        # shape of --json; bump when a field's meaning changes
                                 # 2 (unreleased) = `evidence_quality` is DERIVED and may read
                                 #   DEGRADED/UNKNOWN · `history.quality` is the worst quality of
                                 #   the evidence ELIGIBLE FOR THIS ANALYSIS, and is EMPTY when
                                 #   nothing is comparable · `history.damage` counts the loss
                                 #   boundaries the file holds: `file_global` is every loss a
                                 #   rejected line represents, and `scope_local` maps a scope to
                                 #   the losses its OWN VALIDATED RECORDS reported — never a label
                                 #   read off a line that failed validation, so its keys are always
                                 #   scopes that also appear in `scope.known` · `scope.records_in_scope`
                                 #   counts the whole scope while `scope.records_in_epoch` counts what
                                 #   the current epoch contributes · `history.run_id_conflicts`
                                 #   counts accepted records that repeat a run_id with a DIFFERENT
                                 #   persisted observation, an integrity event that cuts like any
                                 #   other loss and is never reported as a retry · a CANDIDATE outranks
                                 #   PARTIAL_EVIDENCE, because each finding is gated on its own
                                 #   evidence before the run is summarised
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

# ---------------------------------------------------------------- the legacy evidence-quality law
# ONE place decides what a piece of legacy evidence is worth, because the alternative was five:
# load_history checked a vocabulary, comparable() checked two values, analyse() read the live
# sweep's word for it, the trend read nothing at all, and emit_candidates() never asked. A finding
# could then be promoted from a corpus nobody had swept completely.
#
# Worst wins, never a majority: one bounded observation among nine complete ones still means part
# of the evidence was never swept, and nine neighbours cannot launder it.
QUALITY_RANK = {"COMPLETE": 0, "PARTIAL": 1, "DEGRADED": 2, "EMPTY": 3, "UNKNOWN": 4, "INVALID": 5}
SCHEMA_WITH_QUALITY = 2          # the first history schema that records how a sweep was taken
# Two different questions, and conflating them cost a HIGH in review:
#   REQUIRED — what the schema-2 writer ALWAYS wrote, so a record that lacks them cannot attest
#              completeness. Nothing is invented for an older schema; a record that never carried
#              these is UNKNOWN rather than trusted.
#   LOSS     — every counter that, WHEN PRESENT, means evidence was selected and then lost. A
#              reader must honour a loss it can see even if that counter came from a later writer
#              (`malformed_lines` is the 1.3.1-era name, `malformed` the current one).
RECORD_REQUIRED_COUNTERS = ("unreadable", "oversize", "skipped_by_limit")
RECORD_LOSS_COUNTERS = ("unreadable", "oversize", "malformed", "malformed_lines",
                        "identity_changed", "conflicted_sources", "records_rejected")
RECORD_BOUND_COUNTERS = ("skipped_by_limit",)
RECORD_COUNTERS = tuple(dict.fromkeys(RECORD_REQUIRED_COUNTERS + RECORD_LOSS_COUNTERS
                                      + RECORD_BOUND_COUNTERS))
# Set by load_history() when a duplicate run_id shows a worse sweep than the record that survives.
# A private, in-memory annotation; nothing writes it back to a file.
QUALITY_FLOOR = "_evidence_quality_floor"


def worst_quality(qualities):
    """The worst quality in the set. An empty set is COMPLETE: a finding that draws on no sampled
    evidence is not degraded by sampling that had nothing to do with it."""
    worst = "COMPLETE"
    for q in qualities:
        if QUALITY_RANK.get(q, QUALITY_RANK["UNKNOWN"]) > QUALITY_RANK[worst]:
            worst = q if q in QUALITY_RANK else "UNKNOWN"
    return worst


def may_promote(quality, accept_partial):
    """May a finding resting on evidence of this quality become a CANDIDATE?

    `--accept-partial` means one thing: the caller declares the bound they asked for to be the
    intended corpus. It is not a switch for evidence that was lost (DEGRADED), for a record that
    cannot attest itself (UNKNOWN), or for one the producer's own rules call INVALID/EMPTY.
    """
    return quality == "COMPLETE" or (quality == "PARTIAL" and bool(accept_partial))


def _derived_record_quality(rec, schema):
    """What a record's OWN numbers prove, ignoring what it claims."""
    nums = {}
    for k in RECORD_COUNTERS + ("sessions", "turns", "carry_bytes", "scanned"):
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
    if "sessions" in nums and nums.get("turns", 1) == 0:
        # Sessions were counted, so turns were counted. A record reporting sessions without them is
        # not a quiet sweep, it is an impossible one.
        return "INVALID"
    shares = rec.get("shares")
    if isinstance(shares, dict) and "carry_bytes" in nums:
        # Zero carry is a REAL outcome, not a corrupt record: "A session whose every item lands on
        # its final turn carries nothing" (tools/carry.py's own report). The 1.3 writer emits
        # `shares: {}` for it and the current writer guards `if C else {}`. What cannot both be
        # true is a share vector with no carry behind it, or carry with nothing to distribute.
        if nums["carry_bytes"] == 0:
            return "EMPTY" if not shares else "INVALID"
        if not shares:
            return "INVALID"
    if "scanned" in nums and nums["scanned"] < nums.get("sessions", 0):
        # A session is a transcript that was scanned AND cleared the turn floor, so the producer
        # can never report more sessions than it scanned. Forty sessions out of one scanned file
        # is not a sweep that went well; it is a record describing a sweep that cannot have
        # happened. (cross-family review, round 1)
        return "INVALID"
    if any(nums.get(k, 0) for k in RECORD_LOSS_COUNTERS):
        return "DEGRADED"
    if any(nums.get(k, 0) for k in RECORD_BOUND_COUNTERS):
        return "PARTIAL"
    if not all(k in nums for k in ("sessions", "turns", "carry_bytes", "scanned")):
        # Zero counters say "nothing went wrong"; they do not say a sweep happened. A record whose
        # corpus fields are absent entirely has a share vector and no population behind it, and
        # reading its zeroed counters as completeness would trust a measurement nobody took.
        # (cross-family review, round 1)
        return "UNKNOWN"
    if schema >= SCHEMA_WITH_QUALITY and not all(k in nums for k in RECORD_REQUIRED_COUNTERS):
        return "UNKNOWN"              # claims a completeness it cannot show
    return "COMPLETE"


def record_quality(rec):
    """Evidence quality of ONE legacy history record: the worst of what it claims and what it can
    show.

    A record may only ever describe itself as no better than its own numbers. Two ways it fails to
    attest at all: the value is missing or unrecognised, or the record declares a schema older than
    the field itself — schema 0/1 predates `evidence_quality`, so a schema-1 record carrying
    COMPLETE is asserting something its own writer could not have known. That is a claim from a
    hand-edited file or a back-filled migration, not provenance. The record stays readable and
    stays in the report; it simply cannot carry a promotion.
    """
    if not isinstance(rec, dict):
        return "INVALID"
    schema = rec.get("schema_version", 0)
    if isinstance(schema, bool) or not isinstance(schema, int):
        # "2" is a string, 2.0 is a float, True is neither. A version this reader cannot name is
        # not a newer generation to be trusted; it is an older one to be doubted.
        schema = 0
    claimed = rec.get("evidence_quality")
    if not isinstance(claimed, str) or claimed not in QUALITY_RANK:
        claimed = "UNKNOWN"
    if schema < SCHEMA_WITH_QUALITY:
        claimed = "UNKNOWN"
    derived = _derived_record_quality(rec, schema)
    if claimed == "PARTIAL" and derived == "COMPLETE":
        # A bound the caller asked for shows up in `skipped_by_limit`; a loss shows up in a loss
        # counter. A record that says PARTIAL while every counter it carries says nothing happened
        # cannot say WHY it was partial — and `--accept-partial` adopts a bound, not a word.
        # (cross-family review, confirmation round)
        claimed = "UNKNOWN"
    qualities = [claimed, derived]
    floor = rec.get(QUALITY_FLOOR)
    if floor:                         # absent is not UNKNOWN: most records carry no floor at all
        qualities.append(floor)
    return worst_quality(qualities)


def sweep_quality(live):
    """Evidence quality of the LIVE sweep, from the counters carry.accumulate() kept.

    The producer reports one word for two different things (see carry.sweep_label): a bound the
    caller asked for and evidence that was lost both read PARTIAL. Here they separate, because only
    the first is something `--accept-partial` may adopt. The counters are the evidence and the
    label is a summary of them, so the worst of the two governs.
    """
    if not live:
        return "COMPLETE"             # no live sweep is not bad live evidence; it is none
    claimed = live.get("quality")
    if not isinstance(claimed, str) or claimed not in QUALITY_RANK:
        claimed = "COMPLETE"
    if not live.get("sessions"):
        return "INVALID" if live.get("scanned") else "EMPTY"
    if not live.get("turns") or not live.get("carry_bytes", 1):
        # The same impossibility the record law refuses: sessions were counted, so turns were
        # counted. A live dict that says otherwise is not a quiet sweep. `carry_bytes` is absent
        # from the sweep dict itself (the caller sums it), so its absence is not the claim.
        # (cross-family review, round 4)
        return "INVALID"
    derived = "COMPLETE"
    if any(live.get(k) for k in carry.LOSS_FIELDS):
        derived = "DEGRADED"
    elif any(live.get(k) for k in carry.BOUND_FIELDS):
        derived = "PARTIAL"
    return worst_quality([claimed, derived])


# A rejected line is a LOSS by default: the history held something that could not be read as a
# record, and a trend built from the survivors is built over a gap. The exceptions are named, and
# they are the only two things a rejection can be that are not a loss, plus the one shape that was
# never our record to begin with:
#   * a refusal by design — current-generation evidence this optimizer does not read — which is a
#     contract, not a loss, and would otherwise cut every history in the middle of a migration;
#   * a deduplicated retry, which is bookkeeping (its quality already travels via QUALITY_FLOOR);
#   * a well-formed JSON line that is not a carry record at all. In a shared file that is another
#     tool's entry, and treating it as lost evidence would cut a history nothing happened to.
# Listed this way round on purpose: a reason added to valid_record() later defaults to LOSS rather
# than slipping through an allowlist nobody updated. (cross-family review, confirmation round)
NOT_A_LOSS = ("current-generation", "duplicate run_id", "not an object", "no shares",
              "not our record_type")

# The epoch a record belongs to: (file-global losses seen before it, losses seen before it that were
# attributed to ITS scope). A private, in-memory annotation; nothing writes it back to a file.
EPOCH_KEY = "_history_epoch"


def rejection_is_loss(reason):
    """Did this rejected line cost the history a record? -> bool.

    A loss is not a verdict on the file. It is a BOUNDARY at that line's physical position: the
    records before it and the records after it are two populations, and only the newest one may
    support a promotion. The gap stays visible in `history.rejected` and `history.damage`. (The
    first repair made damage permanent instead, and an independent acceptance review blocked it:
    nothing in this product expires, rotates or repairs a history, and no flag adopts a loss, so a
    single crash fragment disabled promotion for every scope, forever.)
    """
    return not any(x in str(reason) for x in NOT_A_LOSS)


def degrades_scope(rec):
    """Does this VALIDATED record's own canonical evidence prove that it lost records? -> bool.

    The one trusted source of a scope-local boundary, and the reason it is trusted is provenance,
    not syntax: the record passed valid_record(), its `scope_id` is the same field every accepted
    record already publishes through `scope.known`, and the damage fact comes from
    RECORD_LOSS_COUNTERS rather than from guessing what a corrupt line meant.

    Only an actual loss qualifies. A bound the caller asked for (PARTIAL), a legacy schema that
    cannot attest completeness (UNKNOWN) and a readable record nothing can be compared with
    (INVALID/EMPTY) are not proof that a line went missing, and must not open an epoch.
    """
    if not isinstance(rec, dict):
        return False
    schema = rec.get("schema_version", 0)
    if isinstance(schema, bool) or not isinstance(schema, int):
        schema = 0
    return _derived_record_quality(rec, schema) == "DEGRADED"


# The reader's own annotations. They are computed while reading, never persisted, and they must
# not take part in deciding what a record IS: otherwise the act of reading a file would make an
# identical retry look like a different observation.
READER_PRIVATE = (EPOCH_KEY, QUALITY_FLOOR)


def observation_digest(rec):
    """A deterministic digest of the PERSISTED observation -> str.

    The whole record participates, not a hand-picked subset: the defect this exists to close was
    caused by an identity that was too weak, and a fingerprint built from a chosen handful would be
    the same mistake in a new spelling. Keys are sorted, so JSON key order and whitespace cannot
    make two semantically identical observations differ, and a persisted field this reader does not
    know still changes the digest — conservatively non-equivalent, which is fail-closed and
    recoverable.
    """
    body = {k: v for k, v in rec.items() if k not in READER_PRIVATE}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def retry_identity(rec):
    """The identity two accepted records must SHARE before they can be the same run -> key | None.

    Scope, because two agents legitimately write at once. The FILE-GLOBAL half of the epoch,
    because across an unattributable loss the reader cannot establish continuity at all and both
    copies stand. Not the scope-local half: a trusted boundary leaves the file intact, so identity
    survives it. A record without a run_id cannot be shown to be anyone's retry and is always its
    own observation.
    """
    rid = rec.get("run_id")
    if not (isinstance(rid, str) and rid):
        return None
    return (scope_of(rec), rec.get(EPOCH_KEY, (0, 0))[0], rid)


# `run_id` is an identity CLAIM, not proof of semantic equality. Two records are the same run only
# when their identity AND their persisted observation match; a same-identity pair whose observations
# differ is an integrity event, not bookkeeping. ONE classification, so the boundary, the
# deduplication, the quality floor and the diagnostics can never disagree about the same pair.
TRUE_RETRY, RUN_ID_CONFLICT, FIRST_SIGHTING = "retry", "conflict", "first"


def classify_repeat(prior_digest, digest):
    """-> TRUE_RETRY | RUN_ID_CONFLICT | FIRST_SIGHTING"""
    if prior_digest is None:
        return FIRST_SIGHTING
    return TRUE_RETRY if prior_digest == digest else RUN_ID_CONFLICT


def active_epoch_key(scope, epochs):
    """The epoch a record of `scope` must carry to be part of the CURRENT analysis."""
    e = epochs or {}
    return (e.get("file_global", 0), (e.get("scope_local") or {}).get(scope, 0))


def active_records(recs, epochs):
    """The records after the newest loss that applies to their own scope.

    A record built in memory rather than read from a file carries no epoch annotation; it belongs
    to the current epoch, because no loss was observed around it.
    """
    out = []
    for r in (recs or []):
        key = active_epoch_key(scope_of(r), epochs)
        if r.get(EPOCH_KEY, key) == key:
            out.append(r)
    return out


def damage_summary(epochs):
    """What the FILE holds, as diagnostics — never a gate. A historical gap can stay true while the
    evidence after it is independently complete.

    `file_global` is every loss a rejected line represents: a rejected line cannot say whose record
    it was, so it cuts every scope at its position. `scope_local` therefore has exactly one source —
    records that PASSED validation and whose own canonical counters reported a loss — and its keys
    are always scopes that also appear in `scope.known`. No attacker-controlled string from a
    rejected line can add a key here, whatever it looks like, and the map's cardinality is bounded
    by the real scopes in the file rather than by the corrupt lines in it."""
    e = epochs or {}
    local = dict(e.get("scope_local") or {})
    return {"boundaries": e.get("file_global", 0) + sum(local.values()),
            "file_global": e.get("file_global", 0), "scope_local": local}


def history_quality(records):
    """The worst quality among the records ELIGIBLE to support a finding.

    Eligibility is not decided here: comparable() already decided it — same scope, same workload
    class, compatible corpus size, quality that can carry a comparison at all. A partial record
    belonging to another agent's scope is not evidence for this run and must not block it. That
    half matters as much as the fail-closed half: a gate that blocks on evidence a finding never
    used is not correct, it is merely stuck.
    """
    if not records:
        # M1 (acceptance review): a machine consumer must never read COMPLETE and conclude that
        # usable history exists. Nothing eligible is EMPTY — the producer's own word for "there was
        # nothing to look at" — and it is refused by the promotion gate like every other non-
        # COMPLETE value. worst_quality([]) keeps meaning COMPLETE: a FINDING that rests on no
        # sampled evidence is not degraded by sampling it never used.
        return "EMPTY"
    return worst_quality([record_quality(r) for r in records])

# machine-readable outcome. The CLI exits 0 for every VALID run by default (a scheduler must not
# treat "nothing to do" as breakage); --strict-exit maps the status to the exit code instead.
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
def safe_label(v):
    """A value read off a rejected line, before it may appear in a public reason string.

    Only a number can be a schema version, so only a number is echoed. Anything else is a corrupt
    line's own content, it carries no diagnostic value beyond its type, and a reason string is
    public output: `history.rejected` keys reach --json, the human report and any log that keeps
    them. Truncating such a value is not a bound — thirty characters of a credential is still the
    credential — so it is named by TYPE and never by content.
    """
    if v is None or (isinstance(v, (int, float)) and not isinstance(v, bool)):
        return repr(v)
    return "of type " + type(v).__name__


def valid_record(o):
    """-> (ok, reason). Malformed input must not poison a trend; it must be counted and dropped."""
    if not isinstance(o, dict):
        return False, "not an object"
    # The v1.4 boundary, stated rather than stumbled into. A current-generation record carries an
    # envelope; this optimizer was written against the flat 1.3 record and does not know what a
    # v1.4 certificate means. Reading one would mean guessing whether its evidence is COMPLETE —
    # the exact "a record gains trust by defaulting" failure, in the direction nobody watches.
    # Refuse it by NAME, and count the refusal, until the optimizer is ported.
    if isinstance(o.get("envelope"), dict):
        return False, ("unsupported schema_version %s: current-generation (v1.4) evidence, "
                       "not read by this optimizer"
                       % safe_label(o["envelope"].get("schema_version")))
    # Computed here and used twice: a rejection's damage class depends on whether the line claimed
    # to be one of OUR records at all.
    claims_ours = (o.get("record_type") == "carry_run" or "schema_version" in o
                   or "run_id" in o or "carry_bytes" in o)
    if o.get("record_type") not in (None, "carry_run"):
        # A record_type this reader cannot name, on a line that ALSO carries our fields, is a
        # corrupted record of ours and therefore a loss. On a line that carries none of them it is
        # another tool's entry in a shared history, and reading it as lost evidence would cut a
        # history nothing happened to — the same distinction `no shares` already makes one check
        # further down. (§6 of the trusted-boundary task: a migration must not read as damage.)
        return False, ("unknown record_type" if claims_ours else "not our record_type")
    sv = o.get("schema_version", 0)
    if not isinstance(sv, int) or isinstance(sv, bool) or sv not in SCHEMA_SUPPORTED:
        # The reason string is public: it becomes a key of `history.rejected`. A rejected line's
        # own content therefore goes through safe_label() before it can be echoed there.
        return False, f"unsupported schema_version {safe_label(sv)}"
    sh = o.get("shares")
    if not isinstance(sh, dict):
        # Two different lines, and the damage classification depends on which one this is: a line
        # that claims to be one of OUR records is a corrupted record (a loss), a line that claims
        # nothing is another tool's entry in a shared file (not ours to lose).
        return False, ("carry record without shares" if claims_ours else "no shares")
    if not sh:
        # An EMPTY share map is what the producer writes for a sweep that measured no carry. It is
        # readable evidence with nothing to compare — record_quality() calls it EMPTY and
        # comparable() leaves it out — and reading it as corruption would cut a history that is
        # perfectly intact. A bare `{"shares": {}}` with no sign of being ours is still foreign.
        if not claims_ours:
            return False, "no shares"
        sh = {}
    for k, v in sh.items():
        if not isinstance(k, str) or not isinstance(v, (int, float)) or isinstance(v, bool):
            return False, "non-numeric share"
        if v < 0 or v > 100.5:
            return False, "share out of range"
    tot = sum(sh.values())
    if sh and not (95.0 <= tot <= 105.0):
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
    sid = o.get("scope_id")
    if sid is not None and (not isinstance(sid, str) or len(sid) > 64):
        # `scope_id` is an ATTRIBUTION AUTHORITY: a validated record's own scope decides which
        # population a loss cut applies to, so the field has to be checked before the record is
        # accepted rather than after. The producer writes exactly one shape —
        # `str(scope_id or "default")[:64]` (tools/carry.py) — so another type or another length
        # was not written by it. Accepting one let `["rev"]` become the scope `"['rev']"`: the cut
        # landed on a population nobody has and the real `rev` records kept crossing the loss,
        # which is the blocked defect rebuilt through the one door this repair opened.
        # (cross-family author review of the trust repair, round 2)
        # The reason is STATIC on purpose: it is a rejected line's own content and must not be
        # echoed. A control character inside a label the PRODUCER wrote is still accepted — it is
        # already published through `scope.known` and calling it corruption would invent damage.
        return False, "scope_id is not a label this producer writes"
    return True, ""


def scope_of(r):
    return str(r.get("scope_id") or "default")


def load_history(path):
    """-> (records, rejected counter, lines, epochs). Deduplication is by run_id within one epoch: two agents can
    legitimately produce the same timestamp, turn count and shares, and discarding one of them
    would undercount the population. A record without a run_id (schema 0/1) cannot be deduplicated
    and is kept as it is."""
    recs, rejected = [], collections.Counter()
    cuts_file, cuts_scope = 0, collections.Counter()
    conflicts, under = 0, {}
    if not path or not os.path.exists(path):
        return recs, rejected, 0, {"file_global": 0, "scope_local": {}, "run_id_conflicts": 0}
    lines = 0
    try:
        # BYTES, decoded strictly per physical line. `errors="replace"` destroyed the evidence that
        # a decode had failed: undecodable bytes inside `scope_id` arrived as U+FFFD, passed for a
        # readable label, and cut a scope that does not exist — while the real population kept
        # crossing the loss. A line the reader cannot decode is named and counted as a loss; the
        # reader then continues at the next line rather than abandoning the file.
        fh = open(path, "rb")
    except OSError as e:
        rejected[f"history unreadable: {safe_err(e)}"] += 1
        # A file that would not open is a loss nobody can attribute: every scope starts a new epoch
        # with no records in it, which is the fail-closed answer.
        return recs, rejected, 0, {"file_global": 1, "scope_local": {}, "run_id_conflicts": 0}
    with fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            lines += 1
            o, ok, why = None, False, ""
            if len(raw) > carry.MAX_RECORD:      # the cap is on BYTES; so is the line that hit it
                why = "record above the size cap"
            else:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    why = "line is not valid UTF-8"
                else:
                    try:
                        o = json.loads(text)
                    except Exception:
                        why = "unparseable line"      # a torn line cannot say whose record it was
                    else:
                        ok, why = valid_record(o)
            if ok:
                # Stamped at READ time, in physical order: the epoch is a position in the file,
                # never a timestamp, because the clock is exactly what a damaged history cannot
                # be trusted about.
                o[EPOCH_KEY] = (cuts_file, cuts_scope[scope_of(o)])
                # ONE classification for the pair, read here and nowhere else. The boundary, the
                # deduplication, the quality floor and the diagnostics all consume this verdict:
                # the defect that produced it was a boundary layer and a dedup layer holding two
                # notions of identity, one of them too coarse.
                ident = retry_identity(o)
                prior = under.get(ident) if ident is not None else None
                digest = observation_digest(o) if ident is not None else None
                verdict = classify_repeat(prior["digest"] if prior else None, digest)
                if verdict == TRUE_RETRY:
                    # The same run reporting the SAME observation again. Dropped as an observation,
                    # counted, and its quality still travels to the copy that survives — a retry
                    # cannot launder a bounded or lossy sweep into a complete one. It opens no
                    # boundary: a repeated copy of one loss is one loss, and letting a late copy
                    # cut again let `6 healthy records + one more copy of X` erase a recovered
                    # epoch, on repeat, forever.
                    rejected["duplicate run_id (retry)"] += 1
                    kept = prior["rec"]
                    worse = worst_quality([record_quality(kept), record_quality(o)])
                    if worse != record_quality(kept):
                        kept[QUALITY_FLOOR] = worse
                    continue
                recs.append(o)
                if ident is not None:
                    # The NEWEST observation is what this identity currently says, so a later exact
                    # copy is that one's retry rather than the original's conflict.
                    under[ident] = {"rec": o, "digest": digest}
                if verdict == RUN_ID_CONFLICT:
                    # Not bookkeeping. The file states two different things under one identity and
                    # the reader cannot tell which one the population it is about to compare
                    # belongs to. Counted as a CONFLICT — reporting it as a retry would be a false
                    # statement — and cut at this record's own physical position, so evidence from
                    # before it is never combined with evidence after it. Recoverable like every
                    # other boundary here: enough clean later evidence promotes normally.
                    conflicts += 1
                if verdict == RUN_ID_CONFLICT or degrades_scope(o):
                    # The record belongs to the epoch it CLOSES: stamped first, counter moved
                    # after it. A population that recovers is not founded on the observation that
                    # reported the loss, nor on the one that contradicted its own identity.
                    cuts_scope[scope_of(o)] += 1
                continue
            rejected[why] += 1
            # EVERY loss a rejected line represents is file-global. A record that failed validation
            # is not a trustworthy authority for its own scope attribution: the field that would
            # name the population is part of the line this reader just refused to believe. Reading
            # it anyway is the fail-open half — it invents a scope that may not exist and leaves
            # the damaged one uncut. This over-blocks on purpose, and the over-block is temporary
            # because epochs recover; a crossing of a real loss is not.
            if rejection_is_loss(why):
                cuts_file += 1
    # Deduplication already happened, in the read pass, in physical order, from the SAME verdict
    # the boundary used. A second pass with its own notion of identity is exactly how the two
    # layers came to disagree about one pair.
    return recs, rejected, lines, {"file_global": cuts_file, "scope_local": dict(cuts_scope),
                                   "run_id_conflicts": conflicts}


def by_scope(recs):
    out = collections.defaultdict(list)
    for r in recs:
        out[scope_of(r)].append(r)
    return dict(out)


def eligible_anchor(recs):
    """The newest record that may speak for a population -> record or None.

    Eligibility comes FIRST. The anchor used to be the newest record of any kind, and the very next
    line threw it away for being INVALID — after it had already decided which scope, which workload
    class and which corpus size every other record was measured against. One broken sweep at the
    top of the file could strand an entire eligible population.
    """
    usable = [r for r in recs if record_quality(r) not in ("INVALID", "EMPTY")]
    return max(usable, key=lambda r: r.get("ts") or 0) if usable else None


def comparable(recs):
    """Records that may be compared with the newest ELIGIBLE one: same scope, same workload class,
    compatible corpus size, quality that can carry a comparison at all.

    INVALID and EMPTY records are dropped here; PARTIAL, DEGRADED and UNKNOWN ones stay, because
    they ARE part of the population and the report should show them. What they cannot do is carry
    a promotion — that is the promotion gate's job, and it reads history_quality() over exactly the
    records this function kept.
    """
    if not recs:
        return [], []
    newest = eligible_anchor(recs)
    if newest is None:
        return [], [(r, "evidence quality " + record_quality(r)) for r in recs]
    n_turn = newest.get("turns") or 0
    n_scope = scope_of(newest)
    n_work = str(newest.get("workload_class") or "")
    keep, dropped = [], []
    for r in recs:
        q = record_quality(r)
        if q in ("INVALID", "EMPTY"):
            dropped.append((r, "evidence quality " + q))
            continue
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
        # A ledger that EXISTS and cannot be read is not the same as no ledger at all: the guard's
        # evidence is missing rather than absent by design, and `rejected` says so.
        return {"writes": 0, "prevented": 0, "rejected": 1, "rate": 0.0, "unreadable": True}
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
            else:
                # Neither a write nor a prevented write: a line this reader cannot account for.
                # Counting it as nothing at all let a ledger full of unknown events look like a
                # clean sample. (cross-family review, confirmation round)
                rejected += 1
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
            evidence_runs=(), global_claim=False):
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
                optimizer_version=OPTIMIZER_VERSION, threshold_schema_version=THRESHOLD_SCHEMA_VERSION,
                samewrite_version=carry.samewrite_version(),
                date=time.strftime("%Y-%m-%d", time.gmtime()))


def analyse(live, hist, ledger, cold, scope="default", accept_partial=False):
    out = []
    # Every candidate-producing path below states which evidence it rests on, and asks the same
    # question about exactly that evidence. A finding drawing on the live sweep is not blocked by a
    # partial history it never read, and a finding drawing on history is not waved through because
    # today's sweep happened to be clean.
    quality = sweep_quality(live) if live else "COMPLETE"
    hist_q = history_quality(hist.get("comparable", []))
    usable = may_promote(quality, accept_partial)            # findings that rest on the live sweep
    hist_usable = may_promote(hist_q, accept_partial)        # findings that rest on the history
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
                out.append(finding(cid, "CANDIDATE", f"{src} dominates carry", ev, scope=scope,
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
                out.append(finding(cid, "OBSERVED", f"{src} dominates carry", ev + " — " + why,
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
            cid = "trend-" + re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-")
            spike = (" — but the last value sits z=%+.1f from its own history, so this slope "
                     "may be one spike rather than a shift" % t["z"]) if abs(t["z"]) >= TREND_MIN_Z else ""
            # DIRECTION, not magnitude. A fitted slope decays as its window grows even when the
            # world stopped moving, so bucketing the magnitude mints a fresh proposal every time
            # the estimator settles. One sustained movement is one proposal; a REVERSAL is a new
            # one, which is exactly when a human should look again.
            direction = 1 if per_month > 0 else -1
            ev = (f"{per_month:+.1f} pp/month over {t['n']} records in scope {scope!r}, "
                  f"last value z={t['z']:+.1f}{spike} (evidence {hist_q})")
            if not hist_usable:
                # The movement is real arithmetic over records that cannot say how they were
                # acquired, so it is reported and never promoted. A trend over bounded sweeps is
                # a trend in the sample, not in the population.
                out.append(finding(cid, "OBSERVED", f"{k} share is moving",
                                   ev + f" — history evidence is {hist_q}, not a population",
                                   scope=scope, bucket=direction,
                                   metric=f"slope of {k} share", invariants=(SCOPE_INVARIANT,)))
            else:
                out.append(finding(cid, "CANDIDATE", f"{k} share is moving", ev, scope=scope,
                                   bucket=direction,
                                   hypothesis=f"the change in {k} is a shift, not a spike, and has a cause worth naming",
                                   metric=f"slope of {k} share", effect="unknown until measured",
                                   risk="a trend can come from the workload, not from SameWrite",
                                   layer="investigation only", always_on_bytes=0, evidence_runs=run_ids,
                                   invariants=(SCOPE_INVARIANT,),
                                   benchmark="identify the cause before proposing a rule"))
    # 3. the guard: does it still pay for itself? (rule retirement is a first-class outcome)
    #    Its evidence is the hook's OWN ledger — writes it saw, no-ops it prevented — not a sample
    #    of transcripts. No sweep or history quality can make it better or worse, so the eligibility
    #    decision here is explicit and separate: the ledger's own sample size is its gate.
    ledger_usable = (bool(ledger) and ledger.get("writes", 0) >= LEDGER_MIN_WRITES
                     and not ledger.get("rejected"))
    if ledger and ledger["writes"]:
        if ledger["writes"] >= LEDGER_MIN_WRITES:
            if ledger["rate"] >= LEDGER_MIN_NOOP_RATE:
                out.append(finding("noop-guard-retain", "OBSERVED", "the no-op guard is still paying",
                                   f"{ledger['prevented']} of {ledger['writes']} writes prevented "
                                   f"({ledger['rate']:.1f}% >= {LEDGER_MIN_NOOP_RATE}%)",
                                   scope=scope, bucket=bucket_of(ledger["rate"]), metric="ledger deny rate"))
            else:
                out.append(finding("noop-guard-retire",
                                   "CANDIDATE" if ledger_usable else "OBSERVED",
                                   "the no-op guard may have stopped paying",
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
            out.append(finding("noop-guard", "OBSERVED", "the guard's field sample is too small to judge",
                               f"{ledger['writes']} writes recorded, need {LEDGER_MIN_WRITES}",
                               scope=scope, metric="ledger deny rate"))
    # 4. the listing this scope pays for on every turn — never a global prune
    if cold:
        share = 100.0 * cold["cold_bytes"] / (cold["total_bytes"] or 1)
        ev = (f"in scope {scope!r}: {cold['cold']}/{cold['entries']} entries never invoked, "
              f"{cold['cold_bytes']:,} of {cold['total_bytes']:,} listing bytes ({share:.1f}%), "
              f"evidence {quality}")
        if share >= COLD_LISTING_MIN_SHARE and cold["cold_bytes"] >= COLD_LISTING_MIN_BYTES and usable:
            out.append(finding("listing-prune", "CANDIDATE",
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
            out.append(finding("listing-prune", "OBSERVED",
                               "skill listing is mostly used, or evidence is not a population", ev, scope=scope,
                               bucket=bucket_of(share), metric="cold share of the skill listing",
                               invariants=(SCOPE_INVARIANT,)))
    return out


def overall_status(findings, hist, live, pop, accept_partial):
    """The run's one word — and the thing that decides whether anything is written.

    CANDIDATE now precedes PARTIAL_EVIDENCE, which it did not before. That is not a loosening: a
    finding only reaches CANDIDATE after its OWN evidence passed the promotion gate, so a run that
    has one is a run whose promoted findings rest on evidence that was eligible. The old order
    blocked a valid history-only finding because today's live sweep happened to be bounded — a
    refusal by evidence the finding never used.
    """
    if pop.get("host_shift"):
        return "HOST_BEHAVIOR_SHIFT"
    if any(f["state"] == "CANDIDATE" for f in findings):
        return "CANDIDATE"
    # Evidence that EXISTS and was refused is a different answer from evidence that is missing:
    # PARTIAL_EVIDENCE tells the caller a flag or a full sweep would change the outcome, while
    # INSUFFICIENT_DATA tells them to keep collecting.
    refused = []
    if live:
        refused.append(sweep_quality(live))
    comp = hist.get("comparable", [])
    if comp:
        refused.append(history_quality(comp))
    elif any(record_quality(r) == "INVALID" for r, _why in hist.get("dropped", [])):
        # Evidence that exists and is refused. EMPTY is NOT one of these: a record that measured
        # nothing is missing evidence, not bad evidence, and "keep collecting" is the honest word
        # for it. A loss does not appear here at all any more — it moved the epoch instead.
        refused.append("INVALID")
    if any(not may_promote(q, accept_partial) for q in refused):
        return "PARTIAL_EVIDENCE"
    if not live and len(comp) < MIN_HISTORY_FOR_TREND:
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


# A candidate_id is a LOGICAL identity: it carries the analysed scope verbatim, because the scope is
# what the finding is about. It used to be the directory name as well, and a scope is an opaque label
# nobody ever validated as a path — `x/../../up` put HYPOTHESIS.md outside the --emit-candidate root
# (issue #15). Identity and storage are two things now; the scope itself is never rewritten.
STORAGE_HASHED_PREFIX = "candidate-sha256-"


def candidate_storage_component(candidate_id):
    """The ONE directory name a logical candidate_id is stored under -> str | None.

    An id that is already one ordinary pathname component is its own name, byte for byte, so every
    directory an existing installation holds keeps its path. An id holding a separator of either
    platform, a dot segment or nothing at all is stored under the SHA-256 of the COMPLETE id:
    deterministic, so an existing candidate is still found; collision-resistant, so two ids never
    share a directory; one component of hex, so it can never be a path. The prefix is reserved — an
    id that already starts with it is hashed too — so a stored name has exactly one logical source.

    None when the id cannot be a pathname at all: an embedded NUL, or text the filesystem encoding
    cannot represent. Hashing those into a name would decide, silently, that such an identity is
    acceptable; the emitter refuses them instead.
    """
    if not isinstance(candidate_id, str) or "\x00" in candidate_id:
        return None
    try:
        os.fsencode(candidate_id)
    except (UnicodeError, ValueError):
        return None
    if (candidate_id in ("", ".", "..") or candidate_id.startswith(STORAGE_HASHED_PREFIX)
            or "/" in candidate_id or "\\" in candidate_id):
        return STORAGE_HASHED_PREFIX + hashlib.sha256(
            candidate_id.encode("utf-8", "surrogatepass")).hexdigest()
    return candidate_id


def candidate_dir(root, candidate_id):
    """The directory a candidate is stored in, under the RESOLVED output root -> path | None.

    The emitter's own containment check, applied whatever the caller handed it rather than trusting
    the mapping above to have been used: the directory must be a direct child of the root by path
    semantics — never a string prefix — and a symlink already sitting at that name is refused, not
    followed out of the root.
    """
    name = candidate_storage_component(candidate_id)
    if name is None:
        return None
    d = os.path.normpath(os.path.join(root, name))
    if os.path.dirname(d) != root:
        return None
    if os.path.islink(d):
        return None
    return d


def emit_candidates(findings, outdir, status):
    """Atomic, deduplicated, never inside a governed tree by default — and only under a status that
    permits promotion at all.

    -> (written, existing, failed). A candidate whose id already exists is NOT rewritten: the
    evidence bucket is part of the id, so a file reappears only when the evidence actually moved.

    The status gate lives HERE rather than at the one call site that used to need it. A status that
    refuses promotion while a file lands on disk is the worst outcome available: the operator reads
    exit 30 or 40 and the next reader of the directory finds a specification that looks approved.
    Putting the gate in the emitter means every caller — the CLI, the long-run simulator, a future
    scheduler — routes through it, and no new caller can forget.
    """
    written, existing, failed = [], [], []
    if status != "CANDIDATE":
        return written, existing, failed
    root = os.path.realpath(outdir)
    for f in findings:
        if f["state"] != "CANDIDATE":
            continue
        # Nothing is inspected or created for a candidate before this answers. The lists below keep
        # naming the LOGICAL id; only the directory is the storage name. (issue #15)
        d = candidate_dir(root, f["candidate_id"])
        if d is None:
            # Static on purpose: the refused id is candidate-controlled text.
            failed.append((f["candidate_id"], "not a single directory inside the output root"))
            continue
        p = os.path.join(d, "HYPOTHESIS.md")
        if os.path.exists(p):
            existing.append(f["candidate_id"])
            continue
        try:
            os.makedirs(d, exist_ok=True)
            tmp = p + ".tmp-%d" % os.getpid()
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(spec_text(f))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, p)             # a crash leaves the old file or the new one, never half
            except OSError:
                # A write that failed mid-way must not leave its half behind: the next reader of
                # this directory would find a file nobody promised. (cross-family review, round 4)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            written.append(f["candidate_id"])
        except OSError as e:
            failed.append((f["candidate_id"], safe_err(e)))
    return written, existing, failed


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
def render(live, hist, ledger, cold, pop, findings, sources, status, scope, scopes_seen):
    L = ["SameWrite Health — evidence-adaptive optimizer", ""]
    L.append(f"status    : {status}   scope: {scope}"
             + (f"   (history also holds: {', '.join(sorted(s for s in scopes_seen if s != scope))})"
                if len(scopes_seen) > 1 else ""))
    L.append("scope")
    epoch_note = ("" if hist.get("in_epoch", hist["in_scope"]) == hist["in_scope"]
                  else f" ({hist.get('in_epoch', 0)} after the newest loss)")
    L.append(f"  history   : {sources['history'] or '(none)'} — {hist['total']} records, "
             f"{hist['in_scope']} in this scope{epoch_note}, {len(hist['comparable'])} comparable, "
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
        L.append(f"  evidence  : {sweep_quality(live)}"
                 + (f" (the sweep reports {live.get('quality')})"
                    if sweep_quality(live) != live.get("quality") else ""))
    if hist["comparable"]:
        L.append(f"  history   : {history_quality(hist['comparable'])} "
                 f"(worst of {len(hist['comparable'])} eligible records)")
    dmg = hist.get("damage") or {}
    if dmg.get("boundaries"):
        L.append(f"  damage    : {dmg['boundaries']} loss boundary/ies in this file "
                 f"({dmg.get('file_global', 0)} unattributable, "
                 f"{sum((dmg.get('scope_local') or {}).values())} scope-local) — evidence from "
                 f"before the newest one is not combined with evidence after it")
    if hist.get("run_id_conflicts"):
        L.append(f"  identity  : {hist['run_id_conflicts']} record(s) repeat a run id with a "
                 f"different observation — an identity contradiction, counted as a conflict and "
                 f"cut where it appears, never reported as a retry")
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

    recs, rejected, lines, epochs = load_history(a.history)
    scopes = by_scope(recs)
    scopes_seen = sorted(scopes) or ["default"]
    # The epoch is selected BEFORE anything is anchored: a record from before the newest loss must
    # not choose the scope, the workload class, the corpus size or the trend for the population
    # that came after it.
    current = active_records(recs, epochs)
    if a.scope_id:
        scope = a.scope_id
    elif recs:
        # Which scope gets analysed is an anchor too: taking the newest record of ANY quality let a
        # single INVALID sweep in another agent's scope send the whole run to a population that was
        # never going to be analysable. The newest record that CAN speak, IN THE CURRENT EPOCH,
        # chooses; if none can, the newest record of that epoch still names it.
        # Nothing from before the newest loss is consulted, not even as a label: the scope travels
        # into every candidate id, so a stale population naming a ledger finding would attach a
        # promotion to a population that no longer exists. (cross-family review of the B1 repair)
        anchor = (eligible_anchor(current)
                  or (max(current, key=lambda r: r.get("ts") or 0) if current else None))
        scope = scope_of(anchor) if anchor is not None else "default"
    else:
        scope = "default"
    scoped = [r for r in current if scope_of(r) == scope]
    keep, dropped = comparable(scoped)
    damage = damage_summary(epochs)
    hist = {"total": len(recs), "in_scope": len(scopes.get(scope, [])), "in_epoch": len(scoped),
            "comparable": keep, "dropped": dropped, "rejected": rejected, "lines": lines,
            "time_order": time_order(keep), "damage": damage,
            "run_id_conflicts": (epochs or {}).get("run_id_conflicts", 0)}
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
        # Selected ONCE, then handed to both consumers. Calling bounded_paths() twice is two
        # selections, and an mtime that becomes unreadable between them is two different samples
        # again — the defect this function exists to close. (cross-family review, round 4)
        selected = carry.bounded_paths(paths, a.max_files)
        live = carry.accumulate(paths, min_turns=a.min_turns, max_files=a.max_files,
                                selected=selected)
        try:
            listing, uses, sess = skills_tool.scan(selected)
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
    findings = analyse(live, hist, ledger, cold, scope=scope, accept_partial=a.accept_partial)
    status = overall_status(findings, hist, live, pop, a.accept_partial)
    sources = {"history": safe(a.history) if os.path.exists(a.history) else "",
               "ledger": safe(a.ledger) if ledger else ""}

    written, existing, failed = [], [], []
    if a.emit_candidate:
        with Lock(os.path.join(a.emit_candidate, ".optimize.lock")) as got:
            if not got:
                status = "ALREADY_RUNNING"
            else:
                written, existing, failed = emit_candidates(findings, a.emit_candidate, status)
                if failed and not written:
                    # The run promised a candidate and nothing landed — an unwritable directory, a
                    # path that is a regular file, a full disk. Reporting CANDIDATE and exit 10
                    # tells a scheduler a specification exists; the status has to say otherwise.
                    # (cross-family review, round 1)
                    status = "INTERNAL_ERROR"

    if a.json:
        print(json.dumps({
            "output_schema_version": OUTPUT_SCHEMA_VERSION,
            "optimizer_version": OPTIMIZER_VERSION,
            "threshold_schema_version": THRESHOLD_SCHEMA_VERSION,
            "samewrite_version": carry.samewrite_version(),
            "history_schema_supported": list(SCHEMA_SUPPORTED),
            "generated": int(time.time()),
            "status": status, "status_code": STATUS.get(status, STATUS["INTERNAL_ERROR"]),
            "scope": {"analysed": scope, "known": scopes_seen,
                      "records_in_scope": len(scopes.get(scope, [])),
                      "records_in_epoch": len(scoped), "comparable": len(keep)},
            # DERIVED, not the producer's summary word: a sweep that lost records reads DEGRADED
            # here even though the 1.3 label for it is PARTIAL (output_schema_version 2).
            "evidence_quality": sweep_quality(live) if live else "NO_SCAN",
            "history": {"records": len(recs), "comparable": len(keep),
                        # the evidence eligible for THIS analysis, not a verdict on the file
                        "quality": history_quality(keep),
                        # ...and what the file holds regardless: a historical gap stays true while
                        # the evidence after it is independently complete
                        "damage": damage,
                        # An observable identity contradiction: two accepted records under one
                        # run_id whose persisted observations differ. A bounded COUNT, never a map
                        # keyed by anything a corrupt file chose — and separate from `rejected`,
                        # because a conflicting record is ACCEPTED and kept, not a line that failed
                        # to become one.
                        "run_id_conflicts": (epochs or {}).get("run_id_conflicts", 0),
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
            "candidates_written": written, "candidates_existing": existing,
            "candidates_failed": [c for c, _ in failed],
            "policy_mutation": False,
        }, indent=2))
    else:
        print(render(live, hist, ledger, cold, pop, findings, sources, status, scope, scopes_seen))
        for c in written:
            print(f"  candidate written: {c}")
        for c in existing:
            print(f"  EXISTING_CANDIDATE (no new action): {c}")
        for c, why in failed:
            print(f"  candidate could NOT be written: {c} — {why}")
    return STATUS.get(status, STATUS["INTERNAL_ERROR"]) if a.strict_exit else 0


if __name__ == "__main__":
    sys.exit(main())
