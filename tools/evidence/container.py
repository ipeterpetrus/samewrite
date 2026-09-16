"""Sections 2b, 4, 6, 8 - container integrity over a VALIDATED container.

The parser hands this module a ValidatedContainer: typed records, plus typed evidence of every
line that did not decode. Rejected lines are part of the container's state, not something the
reader has to remember to count.

CONTAINER INTEGRITY IS GLOBAL. It is determined from the complete validated container evidence
the kernel holds, and never filtered by the population a particular finding analyses. The
previous generation passed an analysis window in here, which made the same container report
different integrity depending on which finding was asking -- and left two paths (the head anchor
and the quarantine binding) that were container-global anyway, contradicting the window rule.
The window is gone; the contradiction it created cannot be expressed.
"""
import dataclasses
import typing

from .absence import Absence
from . import forms as f
from .certificate import MAX_CLOCK_SKEW, MIN_PLAUSIBLE_EPOCH, evaluate_observation
from .closed import Closed, ConstructionError
from .containers import ArchiveWitnesses, HeadEntry, HistoryHead, LedgerCertificate
from .domains import (AcquisitionIntegrity, ContainerIntegrity, DomainError, Reason,
                      require_bool)
from .identity import record_digest
from .records import (HistoryQuarantineEvent, HistoryQuarantineLostEvent, HistoryRestoredEvent,
                      HistoryRotatedEvent, SWEEP_TYPES, ValidatedContainer)
from .values import Digest, Epoch, OrderKey, ScopeId


@dataclasses.dataclass(frozen=True, init=False)
class ContainerState(Closed):
    integrity: ContainerIntegrity
    reasons: typing.Tuple[Reason, ...]
    lines_total: int
    lines_rejected: int
    lines_quarantined: int

    def __repr__(self):
        return "ContainerState(%s, %s)" % (self.integrity.value, [r.value for r in self.reasons])


def make_container_state(integrity, reasons, lines_total, lines_rejected, lines_quarantined,
                         field="container_state"):
    def need(ok, name, detail):
        if not ok:
            raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field + "." + name, detail)
    need(type(integrity) is ContainerIntegrity, "integrity", "a container integrity state")
    need(type(reasons) is tuple and all(type(r) is Reason for r in reasons), "reasons",
         "a tuple of reason codes")
    for name, value in (("lines_total", lines_total), ("lines_rejected", lines_rejected),
                        ("lines_quarantined", lines_quarantined)):
        need(f.is_nat(value), name, "a non-negative int")
    return ContainerState._seal(integrity=integrity, reasons=reasons, lines_total=lines_total,
                                lines_rejected=lines_rejected,
                                lines_quarantined=lines_quarantined)


class _Report(object):
    """Accumulates reasons and the worst state seen, so no branch can forget to worsen."""

    def __init__(self):
        self.reasons = []
        self.state = ContainerIntegrity.INTACT

    def add(self, reason):
        if reason not in self.reasons:
            self.reasons.append(reason)

    def worsen(self, to):
        self.state = ContainerIntegrity.worst(self.state, to)

    def fault(self, reason, to):
        self.add(reason)
        self.worsen(to)


def _seam_ok(records, scope, seq, prev, archives):
    """A record whose predecessor was archived links to the archive's last digest for this scope.

    The rotation record alone cannot establish this -- a writer controls it -- so the caller must
    supply a VERIFIED archive whose digest the rotation names.
    """
    if isinstance(archives, Absence) or not archives.items:
        return False
    active = {record_digest(r) for r in records}
    for rec in records:
        if type(rec) is not HistoryRotatedEvent:
            continue
        body = rec.body
        if body.archive_digest in active:
            continue                       # an archive is never a record still in the active file
        witness = archives.lookup(body.archive_digest)
        if isinstance(witness, Absence):
            continue
        last = witness.last_run_seqs.lookup(scope)
        seam = witness.last_digests.lookup(scope)
        claimed = body.last_run_seqs.lookup(scope)
        if last is None or seam is None or claimed is None:
            continue
        if last == seq - 1 and claimed == last and isinstance(prev, Digest) and prev == seam:
            return True
    return False


def history_integrity(container, head, scope, now, head_required=False,
                      quarantine_file=Absence.UNVERIFIED,
                      archives=Absence.KNOWN_ABSENT):
    """Integrity of one scope's history, over the whole container evidence for that scope."""
    if not isinstance(container, ValidatedContainer):
        raise DomainError("history_integrity takes a ValidatedContainer, got %r"
                          % type(container).__name__)
    if not isinstance(scope, ScopeId):
        raise DomainError("scope is a ScopeId, got %r" % type(scope).__name__)
    if not isinstance(now, Epoch):
        raise DomainError("now is an Epoch, got %r" % type(now).__name__)
    if not isinstance(head, (HistoryHead, Absence)):
        raise DomainError("head is a HistoryHead or an Absence, got %r" % type(head).__name__)
    if not isinstance(archives, (ArchiveWitnesses, Absence)):
        raise DomainError("archives is an ArchiveWitnesses or an Absence")
    if not isinstance(quarantine_file, (Digest, Absence)):
        raise DomainError("quarantine_file is a Digest or an Absence")
    require_bool(head_required, "head_required")

    r = _Report()
    records = container.in_scope(scope)
    legacy = container.legacy_in_scope(scope)
    # a line that did not decode cannot be attributed to a scope, so it counts for the container
    lines_total = len(records) + container.lines_rejected + len(legacy)
    rejected = container.lines_rejected
    if rejected:
        r.fault(Reason.LINE_UNPARSEABLE, ContainerIntegrity.DEGRADED)
    if legacy:
        # a previous wire generation is readable evidence that this reader cannot verify: the
        # chain, the identities and the accounting are all computed under a different schema
        r.fault(Reason.RECORD_UNSUPPORTED_SCHEMA, ContainerIntegrity.UNVERIFIED)

    # --- record level, over every record in scope
    for rec in records:
        if type(rec) in SWEEP_TYPES:
            result = evaluate_observation(rec, now=now)
            if result.derived is AcquisitionIntegrity.UNVERIFIED:
                r.add(Reason.RECORD_SEMANTICALLY_INVALID)
                for code in result.reasons:
                    r.add(code)
                rejected += 1
                r.worsen(ContainerIntegrity.DEGRADED)

    # --- chain, verified and attributed over the whole scope
    groups = {}
    for rec in records:
        groups.setdefault(rec.envelope.run_seq, []).append(rec)
    by_seq = {}
    for seq in sorted(groups):
        members = sorted(groups[seq], key=lambda m: record_digest(m).hex)
        by_seq[seq] = members[0]
        if len(members) == 1:
            continue
        ids = {m.envelope.run_id for m in members}
        contents = {m.equivalence() for m in members}
        prevs = {m.envelope.prev for m in members}
        by_id = {}
        for m in members:
            by_id.setdefault(m.envelope.run_id, []).append(m)
        if any(len({x.equivalence() for x in g}) > 1 for g in by_id.values()):
            r.add(Reason.DEDUP_CONFLICT)
        degrades = True
        if len(ids) > 1:
            r.add(Reason.CHAIN_DUPLICATE_SEQ)
        elif len(contents) > 1:
            r.add(Reason.DEDUP_CONFLICT)
        elif len(prevs) > 1:
            r.add(Reason.CHAIN_DUPLICATE_SEQ)
        else:
            # B.4: an exact repeat IS a retry, and degrading for it would punish the
            # crash-recovery path the contract prescribes
            r.add(Reason.DEDUP_RETRY)
            degrades = False
        if degrades:
            r.worsen(ContainerIntegrity.DEGRADED)

    # a contradiction under one identity is a conflict wherever it sits; distance is not a defence
    by_identity = {}
    for rec in records:
        if type(rec) not in SWEEP_TYPES:
            continue
        by_identity.setdefault((rec.envelope.run_id, rec.envelope.scope), []).append(rec)
    for members in by_identity.values():
        if len(members) < 2:
            continue
        if len({m.equivalence() for m in members}) > 1:
            r.fault(Reason.DEDUP_CONFLICT, ContainerIntegrity.DEGRADED)

    for seq in sorted(by_seq):
        rec = by_seq[seq]
        prev = rec.envelope.prev
        if seq == 0:
            broken = not isinstance(prev, Absence)
        elif seq - 1 in by_seq:
            broken = not (isinstance(prev, Digest) and prev == record_digest(by_seq[seq - 1]))
        else:
            broken = not _seam_ok(records, scope, seq, prev, archives)
        if broken:
            r.fault(Reason.CHAIN_BROKEN, ContainerIntegrity.DEGRADED)

    _head_anchor(r, head, scope, by_seq, records, head_required, lines_total, rejected)
    quarantined = _quarantine(r, records, quarantine_file)
    _restore_floor(r, records)
    return make_container_state(r.state, tuple(r.reasons), lines_total, rejected, quarantined)


def _head_anchor(r, head, scope, by_seq, records, head_required, lines_total, rejected):
    """A head that cannot be read is UNVERIFIED; a head that is absent is a different fact."""
    if head is Absence.UNVERIFIED:
        r.fault(Reason.HEAD_INVALID, ContainerIntegrity.UNVERIFIED)
        return
    entry = Absence.KNOWN_ABSENT if isinstance(head, Absence) else head.entry_for(scope)
    if isinstance(entry, Absence):
        if head_required and (records or rejected):
            r.fault(Reason.HEAD_MISSING, ContainerIntegrity.UNVERIFIED)
        return
    newest = by_seq[max(by_seq)] if by_seq else None
    seen = len(records) + rejected
    if entry.observation_count > seen or (
            newest is not None and entry.highest_run_seq > newest.envelope.run_seq):
        r.fault(Reason.TAIL_TRUNCATED, ContainerIntegrity.UNVERIFIED)
    elif newest is not None and entry.head_digest != record_digest(newest):
        r.fault(Reason.HEAD_STALE, ContainerIntegrity.DEGRADED)
    elif entry.observation_count < seen:
        r.fault(Reason.HEAD_STALE, ContainerIntegrity.DEGRADED)


def _quarantine(r, records, quarantine_file):
    """The bound quarantine file must be THERE. Not looking is not the same as looking and
    finding nothing, and neither is the same as finding it."""
    quarantines = [rec for rec in records if type(rec) is HistoryQuarantineEvent]
    losses = [rec for rec in records if type(rec) is HistoryQuarantineLostEvent]
    quarantined = sum(rec.body.count for rec in quarantines)
    if losses:
        # a record stating that evidence was destroyed cannot leave the container INTACT
        r.fault(Reason.QUARANTINE_LOST, ContainerIntegrity.DEGRADED)
    if not quarantines:
        return quarantined
    # the newest quarantine is chosen by a TOTAL order, so two at one position cannot make the
    # verdict depend on which line the reader saw first
    newest_q = max(quarantines, key=lambda rec: (rec.envelope.run_seq, rec.equivalence().hex))
    acknowledged = any(rec.envelope.run_seq > newest_q.envelope.run_seq for rec in losses)
    bound = newest_q.body.quarantine_file_digest
    if isinstance(quarantine_file, Digest) and quarantine_file == bound:
        return quarantined
    if quarantine_file is Absence.UNVERIFIED:
        r.fault(Reason.QUARANTINE_MISSING, ContainerIntegrity.UNVERIFIED)
    elif acknowledged:
        r.fault(Reason.QUARANTINE_LOST, ContainerIntegrity.DEGRADED)
    else:
        r.fault(Reason.QUARANTINE_MISSING, ContainerIntegrity.UNVERIFIED)
    return quarantined


def _restore_floor(r, records):
    """A restore is a floor, never a ceiling."""
    for rec in records:
        if type(rec) is not HistoryRestoredEvent:
            continue
        floor = rec.body.pre_restore_integrity
        if floor is not ContainerIntegrity.INTACT:
            r.fault(Reason.RESTORE_FLOOR, floor)


def ledger_integrity(certificate, now):
    """Section 8 - the same treatment as an acquisition certificate. No path is exempt."""
    if not isinstance(certificate, (LedgerCertificate, Absence)):
        raise DomainError("ledger_integrity takes a LedgerCertificate or an Absence, got %r"
                          % type(certificate).__name__)
    if not isinstance(now, Epoch):
        raise DomainError("now is an Epoch, got %r" % type(now).__name__)
    if isinstance(certificate, Absence):
        return make_container_state(ContainerIntegrity.UNVERIFIED,
                                    (Reason.LEDGER_UNVERIFIED,), 0, 0, 0)
    c = certificate
    first_absent = isinstance(c.first_ts, Absence)
    last_absent = isinstance(c.last_ts, Absence)
    impossible = [
        c.lines_rejected > c.lines_total,
        c.events_known + c.events_unknown != c.lines_total - c.lines_rejected,
        c.denied > c.checked,
        first_absent != c.is_empty,
        last_absent != c.is_empty,
        (not first_absent and not last_absent and c.first_ts.seconds > c.last_ts.seconds),
        (not last_absent and c.last_ts.seconds > now.seconds + MAX_CLOCK_SKEW),
        (not first_absent and c.first_ts.seconds < MIN_PLAUSIBLE_EPOCH),
        c.checked == 0 and (c.events_known > 0 or c.denied > 0),
        c.writes_observed > c.events_known,
        c.writes_observed > c.checked - c.denied,
    ]
    if any(impossible):
        return make_container_state(ContainerIntegrity.UNVERIFIED,
                                    (Reason.LEDGER_UNVERIFIED,), c.lines_total,
                                    c.lines_rejected, 0)
    if c.lines_rejected > 0 or c.events_unknown > 0:
        return make_container_state(ContainerIntegrity.DEGRADED, (Reason.LEDGER_DEGRADED,),
                                    c.lines_total, c.lines_rejected, 0)
    return make_container_state(ContainerIntegrity.INTACT, (), c.lines_total, c.lines_rejected,
                                0)
