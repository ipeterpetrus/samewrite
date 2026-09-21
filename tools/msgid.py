#!/usr/bin/env python3
"""One assistant message, however many JSONL records carry it.

Claude Code writes one transcript record per CONTENT BLOCK of an assistant message.
A message that thinks, calls a tool and then writes prose is three records, and all
three repeat the same `message.id` and the same `message.usage`. Summing usage per
record therefore bills that message three times, and counting a turn per record
inflates the turn count by the same factor.

Measured here, structure only (tools that read the corpus never read content; this pass
read record `type`, `message.id`, `message.usage`, the guard fields below and block types,
and nothing else). Re-established 2026-09-21 on de-duplicated profile discovery -- the
1.4.1 figures below it counted one archive three times, because three config directories
symlink their `projects/` to the same tree and the old pass predated `os.path.realpath`
de-duplication in tools/profiles.py:

    1,399 transcripts        126,258 assistant records
    65,815 distinct ids      1.92 records per message
    42,793 multi-record messages, usage IDENTICAL in 42,793 of them, 0 differing
    126,257 records carried a usable string id; 1 did not
    every record carried usage; none had an id with usage on some records only
    1 reappearance (a message whose records are not contiguous in file order)
    0 identity collisions on the guard fields below

    (1.4.1, triple-counted archive: 4,143 transcripts / 377,648 records / 196,759 ids /
     127,934 multi-record. The ratios are the same; the absolute counts were not.)

THE LAW

  identity   `message.id` when it is a non-empty string. A record without one is its
             own message — that is what tools/make_fixture.py and the `turn()` helper
             in tests/test_carry.py emit, and keeping their behaviour unchanged is why
             pre-existing fixtures still mean what they meant.

  turn       one per identity, opened by the FIRST RECORD THAT CARRIES THE IDENTITY --
             not by the first record that carries usage. Every block of the message then
             belongs to that turn, including blocks on a record that arrives before the
             usage does, and including a record of an older message that reappears after a
             newer one has already opened. Measured: 1 of 65,815 message openings on the
             de-duplicated corpus is such a reappearance (3 of 197,127 on the tripled one),
             so the shape is rare and real; `out_of_order` counts it rather than leaving it
             to be believed.

  usage      billed once per identity, from the first record of it that carries usage.
             A record that carries NO usage is not a conflict: the message is still one
             message and the copy that does carry usage is the bill. Two records of one
             identity carrying DIFFERENT usage is a USAGE_CONFLICT, and it is not resolved
             -- not first-wins, not last-wins, not max, not sum. No upstream invariant
             authorises any of those, so the ledger refuses to turn the ambiguity into a
             number: `Ambiguous` is raised (strict, the default) or counted (strict=False,
             for the one caller whose job is to report the exclusion).

  collision  a repeated identity whose records disagree on a field PROVEN invariant across
             the records of one message is a MESSAGE_IDENTITY_CONFLICT -- two logical
             messages under one id, detected rather than merged. Proven means measured:
             see GUARD_MESSAGE / GUARD_RECORD below. A field ABSENT on one record is not a
             disagreement, and a reappearing identity is not one either (`out_of_order`
             counts those, and every one of the 42,793 multi-record identities measured here
             agrees on every guard field).

             HONEST LIMIT, now bounded rather than open: two different messages that share
             one id AND agree on every guard field -- same API request id, same model, same
             stop reason -- remain indistinguishable from one multi-block message. That is a
             property of the source format, not of this code; see docs/MEASUREMENT_CORRECTION_1_4_1.md.

  blocks     NOT deduplicated. Identity is a message-level law. The prose block and
             the tool_use block of one message are two distinct items that both belong
             to that message's turn, and both are billed for carry.

Stdlib only, no I/O, no state beyond the ledger you construct.
"""

USAGE_KEYS = ("input_tokens", "output_tokens",
              "cache_read_input_tokens", "cache_creation_input_tokens")

# Fields that every record of one message agreed on, measured over this machine's corpus
# (1,399 transcripts, 126,258 assistant records, 42,793 multi-record identities): 42,793
# agreements and 0 disagreements each, with `requestId` absent on 4,208 records and the
# message-level five absent on none. Fields that DIFFER per record by design -- `uuid`,
# `parentUuid`, `timestamp`, `apiBlockIndex` -- are deliberately absent from this list:
# guarding on one would reject every legitimate multi-block message in the corpus.
# Session-level constants (`sessionId`, `cwd`, `version`, `gitBranch`) are absent for the
# opposite reason: they never differ between two messages of one transcript either, so they
# discriminate nothing. Add a field here only with that table behind it.
GUARD_MESSAGE = ("role", "model", "type", "stop_reason", "stop_sequence")
GUARD_RECORD = ("requestId",)


class Ambiguous(Exception):
    """The transcript does not determine a bill or an identity, and this build will not guess.

    Raised by a strict Ledger, which is the default, so a consumer that adds up usage
    without knowing about conflicts stops instead of publishing an exact-looking number.
    `Ledger(strict=False)` counts instead of raising -- for a caller whose job is to
    report the exclusion rather than to die of it."""

    def __init__(self, kind, field=None):
        self.kind, self.field = kind, field
        super().__init__(f"{kind} conflict" + (f" on {field}" if field else "")
                         + " -- this measurement is not exact and was not resolved")


def identity(msg):
    """-> the assistant message identity, or None when the record carries no usable one.

    A non-string or empty `id` is NOT an identity: merging on it would collapse
    unrelated records, which is the opposite mistake and a worse one."""
    if not isinstance(msg, dict):
        return None
    mid = msg.get("id")
    return mid if isinstance(mid, str) and mid else None


def usage_of(msg):
    """-> the four billed counters of one record as a plain dict of ints."""
    u = (msg or {}).get("usage") or {} if isinstance(msg, dict) else {}
    return {k: (u.get(k) or 0) for k in USAGE_KEYS}


def _key(msg):
    u = usage_of(msg)
    return tuple(u[k] for k in USAGE_KEYS)


def guards(msg, rec=None):
    """-> the proven-invariant metadata this record STATES, as a plain dict.

    A field that is absent, or explicitly null, states nothing and is left out: comparing
    against "not stated" is how a guard starts rejecting legitimate serialisations the day
    the CLI writes `stop_reason` only on the last record of a message."""
    g = {}
    if isinstance(msg, dict):
        for k in GUARD_MESSAGE:
            v = msg.get(k)
            if v is not None:
                g["message." + k] = v
    if isinstance(rec, dict):
        for k in GUARD_RECORD:
            v = rec.get(k)
            if v is not None:
                g[k] = v
    return g


class Ledger:
    """Turn numbering and usage billing for one transcript.

    `observe(msg, rec=None)` once per assistant record, in file order, returns
    `(turn, bill)`: the turn index this record's CONTENT BLOCKS belong to, and whether
    this record's usage is the copy to bill. `bill(msg, rec)` is the same call for
    consumers that only need the second half. `rec` is the whole JSONL record; passing it
    turns on the `requestId` guard, which is the strongest collision guard the format has.
    Leaving it out keeps the message-level guards and nothing breaks.

    Records with no usable identity are each their own message and open a turn only when
    they carry usage -- which is exactly what this repository did before message identity
    existed, and what tools/make_fixture.py and tests/test_carry.py still emit.

    STRICT BY DEFAULT. A usage conflict or an identity collision raises `Ambiguous`, so a
    consumer that sums usage in a loop cannot publish an exact number derived from input
    that does not determine one. `Ledger(strict=False)` counts the same events in
    `usage_conflicts` / `identity_conflicts` and leaves `usage_exact` / `identity_exact`
    False -- for tools/carry.py, whose contract is to EXCLUDE and REPORT the source rather
    than abort a sweep over thousands of files.
    """

    __slots__ = ("_turn", "_usage", "_last", "_guard", "_usage_bad", "_identity_bad",
                 "strict", "turns", "messages", "records",
                 "usage_conflicts", "identity_conflicts", "anonymous", "out_of_order")

    def __init__(self, strict=True):
        self.strict = strict
        self._turn = {}           # identity -> turn index
        self._usage = {}          # identity -> usage tuple billed, or None if not yet
        self._last = None         # identity of the previous identified record
        self._guard = {}          # identity -> {guard field: the value it stated}
        self._usage_bad = set()   # identities whose records disagree on usage
        self._identity_bad = set()  # identities whose records disagree on proven metadata
        self.turns = 0
        self.messages = 0
        self.records = 0
        self.usage_conflicts = 0    # same identity, different usage -- 0 in 42,793 observed
        self.identity_conflicts = 0  # same identity, different PROVEN metadata -- 0 observed
        self.anonymous = 0        # records with no usable identity
        self.out_of_order = 0     # a known identity reappearing after a newer one opened

    # --- what the caller may still treat as exact ---------------------------------
    @property
    def identity_exact(self):
        """False once a detectable collision means turn identity is not determined."""
        return not self.identity_conflicts

    @property
    def usage_exact(self):
        """False once the bill is not determined -- by a usage conflict, or by an identity
        collision, which merges two bills into one and is therefore a usage defect too."""
        return not self.usage_conflicts and not self.identity_conflicts

    @property
    def usage_conflicted_messages(self):
        return len(self._usage_bad)

    @property
    def identity_conflicted_messages(self):
        return len(self._identity_bad)

    def _collide(self, mid, msg, rec):
        """Compare this record's proven-invariant metadata with what the identity already
        stated. Merges fields nobody has stated yet; counts at most one conflict per record."""
        prev = self._guard.setdefault(mid, {})
        bad = None
        for k, v in guards(msg, rec).items():
            if prev.setdefault(k, v) != v and bad is None:
                bad = k
        if bad is None:
            return
        self.identity_conflicts += 1
        self._identity_bad.add(mid)
        if self.strict:
            raise Ambiguous("identity", bad)

    def observe(self, msg, rec=None):
        self.records += 1
        mid = identity(msg)
        has_u = isinstance(msg, dict) and bool(msg.get("usage"))
        if mid is None:
            self.anonymous += 1
            self._last = None      # it broke adjacency: a later repeat IS out of order
            if not has_u:
                return self.turns, False
            self.turns += 1
            self.messages += 1
            return self.turns, True
        if mid in self._turn:
            if self._last != mid:
                self.out_of_order += 1   # legitimate: reappearance is COUNTED, not rejected
            self._last = mid
            self._collide(mid, msg, rec)
            t = self._turn[mid]
            if has_u:
                key = _key(msg)
                if self._usage.get(mid) is None:
                    self._usage[mid] = key     # usage arrived on a later record of it
                    return t, True
                if self._usage[mid] != key:
                    # NOT resolved. first/last/max/min/sum would each need an upstream
                    # invariant to justify it, and no such invariant is established.
                    self.usage_conflicts += 1
                    self._usage_bad.add(mid)
                    if self.strict:
                        raise Ambiguous("usage")
            return t, False
        self.turns += 1
        self.messages += 1
        self._turn[mid] = self.turns
        self._last = mid
        self._guard[mid] = guards(msg, rec)
        self._usage[mid] = _key(msg) if has_u else None
        return self.turns, has_u

    def bill(self, msg, rec=None):
        """-> True when this record's usage is the copy to bill for its message."""
        return self.observe(msg, rec)[1]

    def stats(self):
        return {"messages": self.messages, "turns": self.turns, "records": self.records,
                "usage_conflicts": self.usage_conflicts, "anonymous": self.anonymous,
                "out_of_order": self.out_of_order,
                "identity_conflicts": self.identity_conflicts,
                "usage_conflicted_messages": self.usage_conflicted_messages,
                "identity_conflicted_messages": self.identity_conflicted_messages,
                "usage_exact": self.usage_exact, "identity_exact": self.identity_exact}
