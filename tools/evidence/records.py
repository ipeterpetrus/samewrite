"""The validated history record: one closed type per record KIND.

Phase 1R kept the kind in a field and the shape in a separate type, so `mint` could put an event
kind on a sweep (Review B, B4) and a quarantine body on a sweep envelope (B5). Here the kind IS
the type: there is no field in which a wrong kind can be written, and no body slot on a record
that the contract says has none. The wire parser chooses the variant from `record_type`; after
that the tag and the shape agree because they are the same thing.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .canon import CanonMap, CanonSeq
from .closed import Closed, ConstructionError
from .domains import (AcquisitionIntegrity, ContainerIntegrity, ObservedState, Reason,
                      RecordKind, SamplePolicy, member_of)
from .values import (Digest, Epoch, ManifestEntry, NamedCounts, OrderKey, RunId, ScopeDigests,
                     ScopeId, ScopeSeqs, ShortDigest, SourceId, WorkloadId,
                     digest_of, seq_canon)

RECORD_SCHEMA_VERSION = 4
CERT_SCHEMA_VERSION = 2
LOSS_COUNTERS = ("unreadable", "oversize", "malformed", "records_rejected", "identity_changed",
                 "not_attempted", "dirs_unreadable")
COUNTERS = ("discovered", "skipped_by_limit") + LOSS_COUNTERS + ("empty_source",)


def _require(ok, reason, field, detail):
    if not ok:
        raise ConstructionError(reason, field, detail)


@dataclasses.dataclass(frozen=True, init=False)
class Envelope(Closed):
    """Position and identity. The record KIND is not here: it is the record's type."""
    run_id: RunId
    scope: ScopeId
    run_seq: int
    prev: typing.Union[Digest, Absence]

    @property
    def order(self):
        """Derived, and through the SAME constructor a decoder would use."""
        from .values import make_order_key
        return make_order_key(self.run_seq, self.run_id)

    def canon(self, kind):
        prev = self.prev.hex if type(self.prev) is Digest else None
        return CanonMap([("schema_version", RECORD_SCHEMA_VERSION), ("record_type", kind.value),
                         ("run_id", self.run_id.text), ("scope_id", self.scope.text),
                         ("run_seq", self.run_seq), ("prev_digest", prev)])


@dataclasses.dataclass(frozen=True, init=False)
class AcquisitionCertificate(Closed):
    """Section 3: what the acquisition attempted, reached and lost.

    Everything a reader can DERIVE is gone from the wire and from this object.
    """
    workload: WorkloadId
    sample_policy: SamplePolicy
    sample_bound: typing.Union[int, Absence]
    frozen_selection: typing.Tuple[SourceId, ...]
    discovery_config_digest: Digest
    parser_contract_version: int
    host_profile_id: ShortDigest
    writer_version: str
    completed_at: Epoch
    asserted_integrity: typing.Union[AcquisitionIntegrity, Absence]
    discovered: int
    skipped_by_limit: int
    unreadable: int
    oversize: int
    identity_changed: int
    empty_source: int
    not_attempted: int
    malformed: int
    records_rejected: int
    dirs_unreadable: int

    @property
    def selected(self):
        return len(self.frozen_selection)

    @property
    def skipped_unexamined(self):
        return self.skipped_by_limit

    def canon(self):
        bound = self.sample_bound if type(self.sample_bound) is int else None
        asserted = (self.asserted_integrity.value
                    if type(self.asserted_integrity) is AcquisitionIntegrity else None)
        pairs = [("cert_schema", CERT_SCHEMA_VERSION), ("workload_class", self.workload.text),
                 ("sample_policy", self.sample_policy.value), ("sample_bound", bound),
                 ("frozen_selection", seq_canon(self.frozen_selection)),
                 ("discovery_config_digest", self.discovery_config_digest.hex),
                 ("parser_contract_version", self.parser_contract_version),
                 ("host_profile_id", self.host_profile_id.hex),
                 ("writer_version", self.writer_version),
                 ("completed_at", self.completed_at.seconds),
                 ("asserted_integrity", asserted)]
        pairs += [(name, getattr(self, name)) for name in COUNTERS]
        return CanonMap(pairs)


@dataclasses.dataclass(frozen=True, init=False)
class SweepPayload(Closed):
    """The measurement. `sample_manifest` is already ordered, unique and typed."""
    shares: NamedCounts
    bpt: int
    ts: Epoch
    sessions: int
    turns: int
    carry_bytes: int
    sample_manifest: typing.Tuple[ManifestEntry, ...]

    def canon(self):
        return CanonMap([("shares", self.shares.canon()), ("bpt", self.bpt),
                         ("ts", self.ts.seconds), ("sessions", self.sessions),
                         ("turns", self.turns), ("carry_bytes", self.carry_bytes),
                         ("sample_manifest", seq_canon(self.sample_manifest))])


class _Sweep(object):
    """Shared behaviour of the two sweep variants. Not a base class: a mixin would be a subclass
    relationship, and these types are closed."""


@dataclasses.dataclass(frozen=True, init=False)
class CarrySweep(Closed):
    """A measurement that was taken."""
    envelope: Envelope
    payload: SweepPayload
    certificate: AcquisitionCertificate

    kind = RecordKind.CARRY_SWEEP

    def canon(self):
        return CanonMap([("envelope", self.envelope.canon(self.kind)),
                         ("payload", self.payload.canon()),
                         ("certificate", self.certificate.canon())])

    def equivalence(self):
        """A.5: what the observation SAYS, blind to where it sits and what preceded it."""
        return digest_of(CanonMap([("record_type", self.kind.value),
                                   ("scope_id", self.envelope.scope.text),
                                   ("schema_version", RECORD_SCHEMA_VERSION),
                                   ("payload", self.payload.canon()),
                                   ("certificate", self.certificate.canon())]))


@dataclasses.dataclass(frozen=True, init=False)
class CarrySweepFailed(Closed):
    """A measurement that was ATTEMPTED and produced nothing: section 5's tombstone."""
    envelope: Envelope
    payload: SweepPayload
    certificate: AcquisitionCertificate

    kind = RecordKind.CARRY_SWEEP_FAILED

    def canon(self):
        return CanonMap([("envelope", self.envelope.canon(self.kind)),
                         ("payload", self.payload.canon()),
                         ("certificate", self.certificate.canon())])

    def equivalence(self):
        return digest_of(CanonMap([("record_type", self.kind.value),
                                   ("scope_id", self.envelope.scope.text),
                                   ("schema_version", RECORD_SCHEMA_VERSION),
                                   ("payload", self.payload.canon()),
                                   ("certificate", self.certificate.canon())]))


@dataclasses.dataclass(frozen=True, init=False)
class QuarantineBody(Closed):
    quarantine_file_digest: Digest
    line_digests: typing.Tuple[Digest, ...]
    reason: str

    @property
    def count(self):
        return len(self.line_digests)

    def canon(self):
        return CanonMap([("quarantine_file_digest", self.quarantine_file_digest.hex),
                         ("line_digests", CanonSeq([d.hex for d in self.line_digests])),
                         ("reason", self.reason)])


@dataclasses.dataclass(frozen=True, init=False)
class QuarantineLostBody(Closed):
    expected_file_digest: Digest
    observed_state: ObservedState
    count: int
    reason: str

    def canon(self):
        return CanonMap([("expected_file_digest", self.expected_file_digest.hex),
                         ("observed_state", self.observed_state.value), ("count", self.count),
                         ("reason", self.reason)])


@dataclasses.dataclass(frozen=True, init=False)
class RotationBody(Closed):
    archive_digest: Digest
    archive_last_digests: ScopeDigests
    first_run_seqs: ScopeSeqs
    last_run_seqs: ScopeSeqs
    count: int

    def canon(self):
        return CanonMap([("archive_digest", self.archive_digest.hex),
                         ("archive_last_digests", self.archive_last_digests.canon()),
                         ("first_run_seqs", self.first_run_seqs.canon()),
                         ("last_run_seqs", self.last_run_seqs.canon()),
                         ("count", self.count)])


@dataclasses.dataclass(frozen=True, init=False)
class RestoreBody(Closed):
    restored_digest: Digest
    highest_run_seq: int
    pre_restore_integrity: ContainerIntegrity
    pre_restore_reason: str

    def canon(self):
        return CanonMap([("restored_digest", self.restored_digest.hex),
                         ("highest_run_seq", self.highest_run_seq),
                         ("pre_restore_integrity", self.pre_restore_integrity.value),
                         ("pre_restore_reason", self.pre_restore_reason)])


def _event_canon(event):
    return CanonMap([("envelope", event.envelope.canon(event.kind)),
                     ("body", event.body.canon())])


def _event_equivalence(event):
    """The container's own content digest: A.5 is blind to a body, and A.5 is frozen."""
    return digest_of(CanonMap([("record_type", event.kind.value),
                               ("scope_id", event.envelope.scope.text),
                               ("schema_version", RECORD_SCHEMA_VERSION),
                               ("body", event.body.canon())]))


@dataclasses.dataclass(frozen=True, init=False)
class HistoryQuarantineEvent(Closed):
    envelope: Envelope
    body: QuarantineBody
    kind = RecordKind.HISTORY_QUARANTINE

    def canon(self):
        return _event_canon(self)

    def equivalence(self):
        return _event_equivalence(self)


@dataclasses.dataclass(frozen=True, init=False)
class HistoryQuarantineLostEvent(Closed):
    envelope: Envelope
    body: QuarantineLostBody
    kind = RecordKind.HISTORY_QUARANTINE_LOST

    def canon(self):
        return _event_canon(self)

    def equivalence(self):
        return _event_equivalence(self)


@dataclasses.dataclass(frozen=True, init=False)
class HistoryRotatedEvent(Closed):
    envelope: Envelope
    body: RotationBody
    kind = RecordKind.HISTORY_ROTATED

    def canon(self):
        return _event_canon(self)

    def equivalence(self):
        return _event_equivalence(self)


@dataclasses.dataclass(frozen=True, init=False)
class HistoryRestoredEvent(Closed):
    envelope: Envelope
    body: RestoreBody
    kind = RecordKind.HISTORY_RESTORED

    def canon(self):
        return _event_canon(self)

    def equivalence(self):
        return _event_equivalence(self)


SWEEP_TYPES = (CarrySweep, CarrySweepFailed)
EVENT_TYPES = (HistoryQuarantineEvent, HistoryQuarantineLostEvent, HistoryRotatedEvent,
               HistoryRestoredEvent)
RECORD_TYPES = SWEEP_TYPES + EVENT_TYPES
BODY_FOR_KIND = {HistoryQuarantineEvent: QuarantineBody,
                 HistoryQuarantineLostEvent: QuarantineLostBody,
                 HistoryRotatedEvent: RotationBody,
                 HistoryRestoredEvent: RestoreBody}
EVENT_FOR_KIND = {cls.kind: cls for cls in EVENT_TYPES}
SWEEP_FOR_KIND = {cls.kind: cls for cls in SWEEP_TYPES}


@dataclasses.dataclass(frozen=True, init=False)
class Rejection(Closed):
    """A line that did not decode. It keeps its position and its reasons; it never vanishes."""
    index: int
    reasons: typing.Tuple[Reason, ...]

    def canon(self):
        return CanonMap([("index", self.index),
                         ("reasons", CanonSeq([r.value for r in self.reasons]))])


@dataclasses.dataclass(frozen=True, init=False)
class LegacyRecord(Closed):
    """A record from an earlier wire generation: readable enough to be counted, never enough to
    be promoted. A fact the old schema did not carry stays absent."""
    schema_version: int
    kind: typing.Union[RecordKind, Absence]
    scope: typing.Union[ScopeId, Absence]
    run_seq: typing.Union[int, Absence]
    run_id: typing.Union[RunId, Absence]

    def __repr__(self):
        return "LegacyRecord(schema=%s, scope=%r)" % (self.schema_version, self.scope)


@dataclasses.dataclass(frozen=True, init=False)
class ValidatedContainer(Closed):
    """What decoded, what did not, and what is from an older generation."""
    records: typing.Tuple[object, ...]
    rejections: typing.Tuple[Rejection, ...]
    legacy: typing.Tuple[LegacyRecord, ...]

    @property
    def lines_total(self):
        return len(self.records) + len(self.rejections) + len(self.legacy)

    @property
    def lines_rejected(self):
        return len(self.rejections)

    def in_scope(self, scope):
        return tuple(r for r in self.records if r.envelope.scope == scope)

    def sweeps(self, scope):
        return tuple(r for r in self.in_scope(scope) if type(r) in SWEEP_TYPES)

    def legacy_in_scope(self, scope):
        return tuple(r for r in self.legacy
                     if type(r.scope) is Absence or r.scope == scope)


# --- the authoritative constructors

def make_envelope(run_id, scope, run_seq, prev, field="envelope"):
    _require(type(run_id) is RunId, Reason.ENVELOPE_BAD_TYPE, field + ".run_id",
             "a validated RunId")
    _require(type(scope) is ScopeId, Reason.PATH_LABEL_REJECTED, field + ".scope_id",
             "a validated ScopeId")
    _require(f.is_nat(run_seq), Reason.ENVELOPE_BAD_TYPE, field + ".run_seq",
             "a position is never negative")
    _require(type(prev) is Digest or prev is Absence.KNOWN_ABSENT, Reason.ENVELOPE_BAD_TYPE,
             field + ".prev_digest",
             "a link, or KNOWN_ABSENT for the first record of a scope")
    return Envelope._seal(run_id=run_id, scope=scope, run_seq=run_seq, prev=prev)


def make_certificate(workload, sample_policy, sample_bound, frozen_selection,
                     discovery_config_digest, parser_contract_version, host_profile_id,
                     writer_version, completed_at, asserted_integrity, counters,
                     field="certificate"):
    R = Reason.CERT_BAD_TYPE
    _require(type(workload) is WorkloadId, R, field + ".workload_class", "a validated WorkloadId")
    sample_policy = member_of(SamplePolicy, sample_policy, field + ".sample_policy", R)
    _require(sample_bound is Absence.KNOWN_ABSENT or f.is_pos(sample_bound), R,
             field + ".sample_bound", "a positive int, or KNOWN_ABSENT")
    _require(type(frozen_selection) is tuple, R, field + ".frozen_selection", "a tuple")
    seen = set()
    previous = None
    for source in frozen_selection:
        _require(type(source) is SourceId, Reason.FROZEN_SELECTION_INVALID,
                 field + ".frozen_selection", "a validated SourceId")
        _require(source.path.hex not in seen, Reason.FROZEN_SELECTION_INVALID,
                 field + ".frozen_selection", "duplicate path_digest %r" % source.path.hex)
        # section 4: the selection is CARRIED in canonical order, and a reader never sorts it
        _require(previous is None or previous < source.path.hex,
                 Reason.FROZEN_SELECTION_ORDER_INVALID, field + ".frozen_selection",
                 "carried in canonical order")
        seen.add(source.path.hex)
        previous = source.path.hex
    _require(type(discovery_config_digest) is Digest, R, field + ".discovery_config_digest",
             "a validated Digest")
    _require(f.is_nat(parser_contract_version), R, field + ".parser_contract_version",
             "a non-negative int")
    _require(type(host_profile_id) is ShortDigest, R, field + ".host_profile_id",
             "a validated ShortDigest")
    _require(f.is_str(writer_version), R, field + ".writer_version", "a string")
    _require(type(completed_at) is Epoch, R, field + ".completed_at", "a validated Epoch")
    if asserted_integrity is not Absence.KNOWN_ABSENT:
        asserted_integrity = member_of(AcquisitionIntegrity, asserted_integrity,
                                       field + ".asserted_integrity", R)
    _require(type(counters) is dict and sorted(counters) == sorted(COUNTERS), R,
             field, "exactly the counters %s" % (sorted(COUNTERS),))
    for name in COUNTERS:
        _require(f.is_nat(counters[name]), R, field + "." + name, "a non-negative int")
    return AcquisitionCertificate._seal(
        workload=workload, sample_policy=sample_policy, sample_bound=sample_bound,
        frozen_selection=frozen_selection, discovery_config_digest=discovery_config_digest,
        parser_contract_version=parser_contract_version, host_profile_id=host_profile_id,
        writer_version=writer_version, completed_at=completed_at,
        asserted_integrity=asserted_integrity, **counters)


def make_payload(shares, bpt, ts, sessions, turns, carry_bytes, sample_manifest,
                 field="payload"):
    R = Reason.PAYLOAD_BAD_TYPE
    _require(type(shares) is NamedCounts, R, field + ".shares", "validated NamedCounts")
    for name, value in (("bpt", bpt), ("sessions", sessions), ("turns", turns),
                        ("carry_bytes", carry_bytes)):
        _require(f.is_nat(value), R, field + "." + name, "a non-negative int")
    _require(type(ts) is Epoch, R, field + ".ts", "a validated Epoch")
    _require(type(sample_manifest) is tuple, R, field + ".sample_manifest", "a tuple")
    seen, previous = set(), None
    for entry in sample_manifest:
        _require(type(entry) is ManifestEntry, R, field + ".sample_manifest",
                 "a validated ManifestEntry")
        _require(entry.path.hex not in seen, Reason.MANIFEST_DUPLICATE_PATH,
                 field + ".sample_manifest", "duplicate path_digest %r" % entry.path.hex)
        _require(previous is None or previous < entry.path.hex, Reason.MANIFEST_ORDER_INVALID,
                 field + ".sample_manifest", "carried in canonical order")
        seen.add(entry.path.hex)
        previous = entry.path.hex
    return SweepPayload._seal(shares=shares, bpt=bpt, ts=ts, sessions=sessions, turns=turns,
                              carry_bytes=carry_bytes, sample_manifest=sample_manifest)


def _checked_sweep_members(envelope, payload, certificate, field):
    """Validate the members of a sweep. A predicate, not an authority: it allocates nothing."""
    _require(type(envelope) is Envelope, Reason.ENVELOPE_MISSING_KEY, field + ".envelope",
             "a validated Envelope")
    _require(type(payload) is SweepPayload, Reason.PAYLOAD_MISSING, field + ".payload",
             "a validated SweepPayload")
    _require(type(certificate) is AcquisitionCertificate, Reason.CERT_MISSING_KEY,
             field + ".certificate", "a validated AcquisitionCertificate")


def make_carry_sweep(envelope, payload, certificate, field="carry_sweep"):
    _checked_sweep_members(envelope, payload, certificate, field)
    return CarrySweep._seal(envelope=envelope, payload=payload, certificate=certificate)


def make_carry_sweep_failed(envelope, payload, certificate, field="carry_sweep_failed"):
    _checked_sweep_members(envelope, payload, certificate, field)
    return CarrySweepFailed._seal(envelope=envelope, payload=payload, certificate=certificate)


def make_quarantine_body(quarantine_file_digest, line_digests, reason,
                         field="history_quarantine body"):
    R = Reason.RECORD_SHAPE_INVALID
    _require(type(quarantine_file_digest) is Digest, R, field + ".quarantine_file_digest",
             "a validated Digest")
    _require(type(line_digests) is tuple, R, field + ".line_digests", "a tuple")
    for item in line_digests:
        _require(type(item) is Digest, R, field + ".line_digests", "a validated Digest")
    _require(f.is_str(reason), R, field + ".reason", "a string")
    return QuarantineBody._seal(quarantine_file_digest=quarantine_file_digest,
                                line_digests=line_digests, reason=reason)


def make_quarantine_lost_body(expected_file_digest, observed_state, count, reason,
                              field="history_quarantine_lost body"):
    R = Reason.RECORD_SHAPE_INVALID
    _require(type(expected_file_digest) is Digest, R, field + ".expected_file_digest",
             "a validated Digest")
    observed_state = member_of(ObservedState, observed_state, field + ".observed_state", R)
    _require(f.is_nat(count), R, field + ".count", "a non-negative int")
    _require(f.is_str(reason), R, field + ".reason", "a string")
    return QuarantineLostBody._seal(expected_file_digest=expected_file_digest,
                                    observed_state=observed_state, count=count, reason=reason)


def make_rotation_body(archive_digest, archive_last_digests, first_run_seqs, last_run_seqs,
                       count, field="history_rotated body"):
    R = Reason.RECORD_SHAPE_INVALID
    _require(type(archive_digest) is Digest, R, field + ".archive_digest", "a validated Digest")
    _require(type(archive_last_digests) is ScopeDigests, R, field + ".archive_last_digests",
             "validated ScopeDigests")
    _require(type(first_run_seqs) is ScopeSeqs, R, field + ".first_run_seqs",
             "validated ScopeSeqs")
    _require(type(last_run_seqs) is ScopeSeqs, R, field + ".last_run_seqs", "validated ScopeSeqs")
    _require(f.is_nat(count), R, field + ".count", "a non-negative int")
    return RotationBody._seal(archive_digest=archive_digest,
                              archive_last_digests=archive_last_digests,
                              first_run_seqs=first_run_seqs, last_run_seqs=last_run_seqs,
                              count=count)


def make_restore_body(restored_digest, highest_run_seq, pre_restore_integrity,
                      pre_restore_reason, field="history_restored body"):
    R = Reason.RECORD_SHAPE_INVALID
    _require(type(restored_digest) is Digest, R, field + ".restored_digest",
             "a validated Digest")
    _require(f.is_nat(highest_run_seq), R, field + ".highest_run_seq", "a non-negative int")
    pre_restore_integrity = member_of(ContainerIntegrity, pre_restore_integrity,
                                      field + ".pre_restore_integrity", R)
    _require(f.is_str(pre_restore_reason), R, field + ".pre_restore_reason", "a string")
    return RestoreBody._seal(restored_digest=restored_digest, highest_run_seq=highest_run_seq,
                             pre_restore_integrity=pre_restore_integrity,
                             pre_restore_reason=pre_restore_reason)


def _checked_event_members(event_type, envelope, body, field):
    """Validate the members of an event. The kind IS the type, so the only relation left is that
    the body is the body of THIS event -- which no caller can get wrong by writing a field."""
    _require(type(envelope) is Envelope, Reason.ENVELOPE_MISSING_KEY, field + ".envelope",
             "a validated Envelope")
    _require(type(body) is BODY_FOR_KIND[event_type], Reason.RECORD_SHAPE_INVALID,
             field + ".body", "a %s" % BODY_FOR_KIND[event_type].__name__)


def make_quarantine_event(envelope, body, field="history_quarantine"):
    _checked_event_members(HistoryQuarantineEvent, envelope, body, field)
    return HistoryQuarantineEvent._seal(envelope=envelope, body=body)


def make_quarantine_lost_event(envelope, body, field="history_quarantine_lost"):
    _checked_event_members(HistoryQuarantineLostEvent, envelope, body, field)
    return HistoryQuarantineLostEvent._seal(envelope=envelope, body=body)


def make_rotation_event(envelope, body, field="history_rotated"):
    _checked_event_members(HistoryRotatedEvent, envelope, body, field)
    return HistoryRotatedEvent._seal(envelope=envelope, body=body)


def make_restore_event(envelope, body, field="history_restored"):
    _checked_event_members(HistoryRestoredEvent, envelope, body, field)
    return HistoryRestoredEvent._seal(envelope=envelope, body=body)


def make_rejection(index, reasons, field="rejection"):
    R = Reason.RECORD_SHAPE_INVALID
    _require(f.is_nat(index), R, field + ".index", "a line index")
    _require(type(reasons) is tuple and reasons, R, field + ".reasons", "a non-empty tuple")
    for reason in reasons:
        _require(type(reason) is Reason, R, field + ".reasons", "a reason code")
    return Rejection._seal(index=index, reasons=reasons)


def make_legacy_record(schema_version, kind, scope, run_seq, run_id, field="legacy"):
    R = Reason.RECORD_UNSUPPORTED_SCHEMA
    _require(f.is_int(schema_version), R, field + ".schema_version", "an int")
    if type(kind) is not Absence:
        kind = member_of(RecordKind, kind, field + ".record_type", R)
    _require(type(scope) is ScopeId or type(scope) is Absence, R, field + ".scope_id",
             "a validated ScopeId, or an absence")
    _require(f.is_nat(run_seq) or type(run_seq) is Absence, R, field + ".run_seq",
             "a position, or an absence")
    _require(type(run_id) is RunId or type(run_id) is Absence, R, field + ".run_id",
             "a validated RunId, or an absence")
    return LegacyRecord._seal(schema_version=schema_version, kind=kind, scope=scope,
                              run_seq=run_seq, run_id=run_id)


def make_container(records, rejections, legacy, field="container"):
    R = Reason.RECORD_SHAPE_INVALID
    for name, values, kinds in (("records", records, RECORD_TYPES),
                                ("rejections", rejections, (Rejection,)),
                                ("legacy", legacy, (LegacyRecord,))):
        _require(type(values) is tuple, R, field + "." + name, "a tuple")
        for value in values:
            _require(type(value) in kinds, R, field + "." + name,
                     "a validated %s" % name[:-1])
    return ValidatedContainer._seal(records=records, rejections=rejections, legacy=legacy)
