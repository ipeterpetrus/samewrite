"""The history mutation protocol: one lock order, one journal, one recovery rule.

A fact recovery does not have is not a fact it may assume.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .closed import Closed, ConstructionError
from .domains import ContainerIntegrity, MutatingOp, Reason, member_of

LOCK_ORDER = ("history_append_lock", "emit_lock")


class TransactionError(ValueError):
    """An operation the recovery rules do not cover, or a fact recovery needs and lacks."""


def _require(ok, field, detail):
    if not ok:
        raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field, detail)


@dataclasses.dataclass(frozen=True, init=False)
class TransactionFacts(Closed):
    op: typing.Union[MutatingOp, Absence]
    txn_open: bool
    journalled_record_present: typing.Union[bool, Absence]
    records_still_in_active: typing.Union[bool, Absence]
    tmp_present: typing.Union[bool, Absence]
    archive_present: typing.Union[bool, Absence]
    head_matches_active: typing.Union[bool, Absence]


@dataclasses.dataclass(frozen=True, init=False)
class Recovery(Closed):
    action: str
    integrity: ContainerIntegrity
    reason: typing.Union[str, Absence]

    def __repr__(self):
        return "Recovery(%s, %s, %s)" % (self.action, self.integrity.value, self.reason)


OPTIONAL_FACTS = ("journalled_record_present", "records_still_in_active", "tmp_present",
                  "archive_present", "head_matches_active")
ACTIONS = ("none", "commit_only", "commit_and_repair_head", "reappend_record", "retry",
           "delete_tmp_and_retry", "discard_archive_and_retry")


def make_transaction_facts(op, txn_open, facts, field="facts"):
    if type(op) is not Absence:
        op = member_of(MutatingOp, op, field + ".op", Reason.RECORD_SHAPE_INVALID)
    _require(f.is_bool(txn_open), field + ".txn_open", "exactly true or false")
    _require(type(facts) is dict and sorted(facts) == sorted(OPTIONAL_FACTS), field,
             "exactly the optional facts %s" % (sorted(OPTIONAL_FACTS),))
    for name in OPTIONAL_FACTS:
        value = facts[name]
        _require(f.is_bool(value) or type(value) is Absence, field + "." + name,
                 "exactly true or false, KNOWN_ABSENT or UNVERIFIED")
    return TransactionFacts._seal(op=op, txn_open=txn_open, **facts)


def make_recovery(action, integrity, reason, field="recovery"):
    _require(action in ACTIONS, field + ".action", "one of %s" % (ACTIONS,))
    integrity = member_of(ContainerIntegrity, integrity, field + ".integrity",
                          Reason.RECORD_SHAPE_INVALID)
    _require(f.is_str(reason) or reason is Absence.KNOWN_ABSENT, field + ".reason",
             "a reason, or KNOWN_ABSENT")
    return Recovery._seal(action=action, integrity=integrity, reason=reason)


def _known(value, name):
    if type(value) is Absence:
        raise TransactionError("recovery needs %s and the caller could not establish it" % name)
    return value


def recover(facts):
    """Decide the recovery from observable facts alone. Never INTACT while a transaction is open."""
    if type(facts) is not TransactionFacts:
        raise TransactionError("recover takes TransactionFacts, got %r" % type(facts).__name__)
    if not facts.txn_open:
        return make_recovery("none", ContainerIntegrity.INTACT, Absence.KNOWN_ABSENT)
    if type(facts.op) is Absence:
        raise TransactionError("an open transaction with no operation has no recovery rule")

    if facts.op is MutatingOp.APPEND:
        landed = _known(facts.journalled_record_present, "journalled_record_present")
        if landed:
            if _known(facts.head_matches_active, "head_matches_active"):
                return make_recovery("commit_only", ContainerIntegrity.DEGRADED, "head_stale")
            return make_recovery("commit_and_repair_head", ContainerIntegrity.DEGRADED,
                                 "head_stale")
        return make_recovery("reappend_record", ContainerIntegrity.DEGRADED, "head_stale")

    if facts.op is MutatingOp.QUARANTINE or facts.op is MutatingOp.ROTATE:
        reason = ("quarantine_incomplete" if facts.op is MutatingOp.QUARANTINE
                  else "rotation_incomplete")
        if not _known(facts.records_still_in_active, "records_still_in_active"):
            return make_recovery("reappend_record", ContainerIntegrity.UNVERIFIED, reason)
        if _known(facts.tmp_present, "tmp_present"):
            return make_recovery("delete_tmp_and_retry", ContainerIntegrity.DEGRADED, reason)
        if facts.op is MutatingOp.ROTATE and _known(facts.archive_present, "archive_present"):
            return make_recovery("discard_archive_and_retry", ContainerIntegrity.DEGRADED,
                                 reason)
        return make_recovery("retry", ContainerIntegrity.DEGRADED, reason)

    return make_recovery("reappend_record", ContainerIntegrity.UNVERIFIED,
                         "restore_unverifiable")
