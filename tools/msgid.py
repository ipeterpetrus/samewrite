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

  turn       one per identity, opened by the first record that carries it.

  usage      billed once per identity, from the first record that carries it. The
             corpus shows every copy identical, so "first" and "last" are the same
             number today; `usage_conflicts` counts the day that stops being true
             instead of silently picking a winner.

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


class Ledger:
    """Answers one question per assistant record: is this the record to bill?

    Call `bill(msg)` once per assistant record, in file order. It returns True exactly
    once per assistant message — on the first record of that message that carries
    usage — and False for every further record of the same message. Records with no
    usable identity are each their own message, so legacy and synthetic transcripts
    keep one-record-one-message.
    """

    __slots__ = ("_billed", "messages", "records", "usage_conflicts", "anonymous")

    def __init__(self):
        self._billed = {}         # identity -> the usage tuple already billed for it
        self.messages = 0         # assistant messages billed
        self.records = 0          # assistant records observed
        self.usage_conflicts = 0  # same identity, different usage — 0 in 127,934 observed
        self.anonymous = 0        # records with no usable identity

    def bill(self, msg):
        self.records += 1
        u = usage_of(msg)
        key = tuple(u[k] for k in USAGE_KEYS)
        has_usage = isinstance(msg, dict) and bool(msg.get("usage"))
        mid = identity(msg)
        if mid is None:
            # No identity to merge on. One record, one message — but only a record that
            # carries usage opens a turn, which is what this repo has always done.
            if has_usage:
                self.anonymous += 1
                self.messages += 1
                return True
            return False
        prev = self._billed.get(mid)
        if prev is None:
            # Identity not billed yet. Only a record that carries usage can bill it; a
            # usage-less first record leaves the message open for a later one.
            if not has_usage:
                return False
            self._billed[mid] = key
            self.messages += 1
            return True
        if has_usage and prev != key:
            self.usage_conflicts += 1
        return False

    def stats(self):
        return {"messages": self.messages, "records": self.records,
                "usage_conflicts": self.usage_conflicts, "anonymous": self.anonymous}
