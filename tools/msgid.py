#!/usr/bin/env python3
"""One assistant message, however many JSONL records carry it.

Claude Code writes one transcript record per CONTENT BLOCK of an assistant message.
A message that thinks, calls a tool and then writes prose is three records, and all
three repeat the same `message.id` and the same `message.usage`. Summing usage per
record therefore bills that message three times, and counting a turn per record
inflates the turn count by the same factor.

Measured here, structure only, before this module existed (tools that read the corpus
never read content; this pass read `type`, `message.id`, `message.usage` and block
types and nothing else):

    4,143 transcripts        377,648 assistant records
    196,759 distinct ids     1.92 records per message
    127,934 multi-record messages, usage IDENTICAL in 127,934 of them, 0 differing
    377,645 records carried a usable string id; 3 did not
    every record carried usage; none had an id with usage on some records only

THE LAW

  identity   `message.id` when it is a non-empty string. A record without one is its
             own message — that is what tools/make_fixture.py and the `turn()` helper
             in tests/test_carry.py emit, and keeping their behaviour unchanged is why
             pre-existing fixtures still mean what they meant.

  turn       one per identity, opened by the FIRST RECORD THAT CARRIES THE IDENTITY --
             not by the first record that carries usage. Every block of the message then
             belongs to that turn, including blocks on a record that arrives before the
             usage does, and including a record of an older message that reappears after a
             newer one has already opened. Measured: 3 of 197,127 message openings in this
             corpus are such a reappearance, all in one transcript, so the shape is rare
             and real; `out_of_order` counts it rather than leaving it to be believed.

  usage      billed once per identity, from the first record of it that carries usage. The
             corpus shows every copy identical, so first and last are the same number
             today; `usage_conflicts` counts the day that stops being true, and
             tools/carry.py aggregates it and prints it, so the counter is a signal rather
             than a private field.

             HONEST LIMIT: two genuinely different messages that shared one id would merge
             here, and nothing in a transcript could distinguish that from one message
             written twice. This law assumes vendor message ids identify a message. What it
             does not do is assume it silently -- a reappearance is counted.

  blocks     NOT deduplicated. Identity is a message-level law. The prose block and
             the tool_use block of one message are two distinct items that both belong
             to that message's turn, and both are billed for carry.

Stdlib only, no I/O, no state beyond the ledger you construct.
"""

USAGE_KEYS = ("input_tokens", "output_tokens",
              "cache_read_input_tokens", "cache_creation_input_tokens")


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


class Ledger:
    """Turn numbering and usage billing for one transcript.

    `observe(msg)` once per assistant record, in file order, returns
    `(turn, bill)`: the turn index this record's CONTENT BLOCKS belong to, and whether
    this record's usage is the copy to bill. `bill(msg)` is the same call for consumers
    that only need the second half.

    Records with no usable identity are each their own message and open a turn only when
    they carry usage -- which is exactly what this repository did before message identity
    existed, and what tools/make_fixture.py and tests/test_carry.py still emit.
    """

    __slots__ = ("_turn", "_usage", "_last", "turns", "messages", "records",
                 "usage_conflicts", "anonymous", "out_of_order")

    def __init__(self):
        self._turn = {}           # identity -> turn index
        self._usage = {}          # identity -> usage tuple billed, or None if not yet
        self._last = None         # identity of the previous identified record
        self.turns = 0
        self.messages = 0
        self.records = 0
        self.usage_conflicts = 0  # same identity, different usage -- 0 in 127,934 observed
        self.anonymous = 0        # records with no usable identity
        self.out_of_order = 0     # a known identity reappearing after a newer one opened

    def observe(self, msg):
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
                self.out_of_order += 1
            self._last = mid
            t = self._turn[mid]
            if has_u:
                key = _key(msg)
                if self._usage.get(mid) is None:
                    self._usage[mid] = key     # usage arrived on a later record of it
                    return t, True
                if self._usage[mid] != key:
                    self.usage_conflicts += 1
            return t, False
        self.turns += 1
        self.messages += 1
        self._turn[mid] = self.turns
        self._last = mid
        self._usage[mid] = _key(msg) if has_u else None
        return self.turns, has_u

    def bill(self, msg):
        """-> True when this record's usage is the copy to bill for its message."""
        return self.observe(msg)[1]

    def stats(self):
        return {"messages": self.messages, "turns": self.turns, "records": self.records,
                "usage_conflicts": self.usage_conflicts, "anonymous": self.anonymous,
                "out_of_order": self.out_of_order}
