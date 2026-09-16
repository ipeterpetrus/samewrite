"""Every finite domain in the contract, as a real type.

A string that travels into an algorithm is a string the algorithm has to re-check. An enum member
cannot be misspelled, cannot be widened by a caller, and cannot be compared against a value from
another domain without the comparison being obviously wrong.
"""
import enum


class DomainError(ValueError):
    """A value outside a declared domain reached a typed algorithm."""


class _Ordered(enum.Enum):
    """An enum whose declaration order IS the contract's order, worst last."""

    @property
    def rank(self):
        return type(self)._members().index(self)

    @classmethod
    def _members(cls):
        return list(cls)

    @classmethod
    def worst(cls, *values):
        if not values:
            raise DomainError("worst() over an empty set of %s" % cls.__name__)
        out = None
        for v in values:
            if not isinstance(v, cls):
                raise DomainError("%r is not a %s" % (v, cls.__name__))
            if out is None or v.rank > out.rank:
                out = v
        return out


class AcquisitionIntegrity(_Ordered):
    """Section 2, axis one: what the acquisition was able to observe."""
    INTACT = "INTACT"
    BOUNDED = "BOUNDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNVERIFIED = "UNVERIFIED"


class AnalysisSufficiency(_Ordered):
    """Section 2, axis two: whether what was observed is enough to answer the question.

    Kept a separate type on purpose. The two axes were merged once, and every operator who read
    the merged value learned to ignore the state that also means forged.
    """
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class ContainerIntegrity(_Ordered):
    """Sections 2b/6/8: the history file and the ledger as containers."""
    INTACT = "INTACT"
    DEGRADED = "DEGRADED"
    UNVERIFIED = "UNVERIFIED"


class ArtifactClassification(_Ordered):
    """Section 11, worst last."""
    PROVEN_CURRENT = "PROVEN_CURRENT"
    STALE = "STALE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNVERIFIABLE = "UNVERIFIABLE"


class RecordKind(enum.Enum):
    CARRY_SWEEP = "carry_sweep"
    CARRY_SWEEP_FAILED = "carry_sweep_failed"
    HISTORY_QUARANTINE = "history_quarantine"
    HISTORY_QUARANTINE_LOST = "history_quarantine_lost"
    HISTORY_ROTATED = "history_rotated"
    HISTORY_RESTORED = "history_restored"

    @property
    def is_sweep(self):
        return self in (RecordKind.CARRY_SWEEP, RecordKind.CARRY_SWEEP_FAILED)

    @property
    def is_event(self):
        return not self.is_sweep


class SamplePolicy(enum.Enum):
    ALL = "all"
    NEWEST_N = "newest_n"


class ObservedState(enum.Enum):
    """What a quarantine-loss event found where the quarantine file should have been."""
    ABSENT = "absent"
    MISMATCH = "mismatch"


class WorldState(enum.Enum):
    SINGLE_WORLD = "SINGLE_WORLD"
    MIXED_WORLD = "MIXED_WORLD"


class FindingState(enum.Enum):
    OBSERVED = "OBSERVED"
    ELIGIBLE = "ELIGIBLE"


class Persistence(enum.Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    WRITTEN = "WRITTEN"
    ALREADY_CURRENT = "ALREADY_CURRENT"
    REFUSED = "REFUSED"
    FAILED = "FAILED"


class IneligibleReason(enum.Enum):
    EVIDENCE_INTEGRITY = "evidence_integrity"
    MIXED_WORLD = "mixed_world"
    CONTAINER_DEGRADED = "container_degraded"
    BOUNDED_UNACCEPTED = "bounded_unaccepted"
    INSUFFICIENT = "insufficient"

    @property
    def is_evidence_failure(self):
        return self in (IneligibleReason.EVIDENCE_INTEGRITY, IneligibleReason.MIXED_WORLD,
                        IneligibleReason.CONTAINER_DEGRADED)


class RunStatus(enum.Enum):
    """Exit code 30 (HOST_BEHAVIOR_SHIFT) was retired with host-shift gating; it is not reused."""
    OBSERVATION_LOST = ("OBSERVATION_LOST", 51)
    EMISSION_FAILED = ("EMISSION_FAILED", 50)
    CANDIDATE_REVIEW_REQUIRED = ("CANDIDATE_REVIEW_REQUIRED", 11)
    CANDIDATE = ("CANDIDATE", 10)
    DEGRADED_EVIDENCE = ("DEGRADED_EVIDENCE", 41)
    BOUNDED_EVIDENCE = ("BOUNDED_EVIDENCE", 40)
    INSUFFICIENT_DATA = ("INSUFFICIENT_DATA", 20)
    NO_ACTION = ("NO_ACTION", 0)

    @property
    def exit_code(self):
        return self.value[1]

    @property
    def writes_artifacts(self):
        return self in (RunStatus.EMISSION_FAILED, RunStatus.CANDIDATE_REVIEW_REQUIRED,
                        RunStatus.CANDIDATE)


class MutatingOp(enum.Enum):
    APPEND = "append"
    QUARANTINE = "quarantine"
    ROTATE = "rotate"
    RESTORE = "restore"


class Reason(enum.Enum):
    """The stable reason vocabulary. An output domain, so it is a type here too."""
    LINE_UNPARSEABLE = "line_unparseable"
    RECORD_SHAPE_INVALID = "record_shape_invalid"
    RECORD_UNSUPPORTED_SCHEMA = "record_unsupported_schema"
    RECORD_UNKNOWN_TYPE = "record_unknown_type"
    RECORD_SEMANTICALLY_INVALID = "record_semantically_invalid"
    RECORD_UNREADABLE = "record_unreadable"
    ENVELOPE_MISSING_KEY = "envelope_missing_key"
    ENVELOPE_UNKNOWN_KEY = "envelope_unknown_key"
    ENVELOPE_BAD_TYPE = "envelope_bad_type"
    PATH_LABEL_REJECTED = "path_label_rejected"
    CERT_MISSING_KEY = "cert_missing_key"
    CERT_UNKNOWN_KEY = "cert_unknown_key"
    CERT_BAD_TYPE = "cert_bad_type"
    CERT_UNSUPPORTED_SCHEMA = "cert_unsupported_schema"
    CERT_ACCOUNTING_VIOLATION = "cert_accounting_violation"
    CERT_IMPOSSIBLE_RELATION = "cert_impossible_relation"
    CERT_CONSERVATION_VIOLATION = "cert_conservation_violation"
    TOMBSTONE_INCONSISTENT = "tombstone_inconsistent"
    PAYLOAD_MISSING = "payload_missing"
    PAYLOAD_MISSING_KEY = "payload_missing_key"
    PAYLOAD_UNKNOWN_KEY = "payload_unknown_key"
    PAYLOAD_BAD_TYPE = "payload_bad_type"
    MANIFEST_DUPLICATE_PATH = "manifest_duplicate_path"
    MANIFEST_COUNT_MISMATCH = "manifest_count_mismatch"
    MANIFEST_NOT_SUBSET = "manifest_not_subset"
    MANIFEST_ORDER_INVALID = "manifest_order_invalid"
    FROZEN_SELECTION_INVALID = "frozen_selection_invalid"
    FROZEN_SELECTION_ORDER_INVALID = "frozen_selection_order_invalid"
    SOURCE_UNREADABLE = "source_unreadable"
    SOURCE_OVERSIZE = "source_oversize"
    SOURCE_IDENTITY_CHANGED = "source_identity_changed"
    SOURCE_NOT_ATTEMPTED = "source_not_attempted"
    DISCOVERY_INCOMPLETE = "discovery_incomplete"
    CHAIN_BROKEN = "chain_broken"
    CHAIN_DUPLICATE_SEQ = "chain_duplicate_seq"
    DEDUP_CONFLICT = "dedup_conflict"
    DEDUP_RETRY = "dedup_retry"
    HEAD_INVALID = "head_invalid"
    HEAD_MISSING = "head_missing"
    HEAD_STALE = "head_stale"
    TAIL_TRUNCATED = "tail_truncated"
    QUARANTINE_MISSING = "quarantine_missing"
    QUARANTINE_LOST = "quarantine_lost"
    RESTORE_FLOOR = "restore_floor"
    LEDGER_MISSING_KEY = "ledger_missing_key"
    LEDGER_UNKNOWN_KEY = "ledger_unknown_key"
    LEDGER_BAD_TYPE = "ledger_bad_type"
    LEDGER_UNVERIFIED = "ledger_unverified"
    LEDGER_DEGRADED = "ledger_degraded"
    ARTIFACT_UNREADABLE = "artifact_unreadable"
    ARTIFACT_HARDLINKED = "artifact_hardlinked"
    ARTIFACT_INTERNAL_MISMATCH = "artifact_internal_mismatch"
    ARTIFACT_BINDING_MISMATCH = "artifact_binding_mismatch"
    ARTIFACT_CONTAINER_DEGRADED = "artifact_container_degraded"
    ARTIFACT_EVIDENCE_NOT_PROMOTABLE = "artifact_evidence_not_promotable"
    ARTIFACT_STALE = "artifact_stale"
    WORLD_UNVERIFIED = "world_unverified"
    WORLD_ID_MISMATCH = "world_id_mismatch"
    SAMPLE_ID_MISMATCH = "sample_id_mismatch"
    SCOPE_ID_MISMATCH = "scope_id_mismatch"

    def __repr__(self):
        return "Reason.%s" % self.name


def require(value, kind, name):
    """Every public entry point states the type it takes, and refuses anything else by name.

    The typed signature is the precondition; this is the runtime half of it, because Python does
    not enforce annotations and a public function that assumes its argument is typed is exactly
    the defect this phase exists to remove.
    """
    kinds = kind if type(kind) is tuple else (kind,)
    if not all(isinstance(k, type) for k in kinds):
        raise DomainError("require() takes a type or a tuple of types, got %r" % (kind,))
    if not isinstance(value, kinds):
        names = "/".join(k.__name__ for k in kinds)
        raise DomainError("%s must be a %s, got %r" % (name, names, type(value).__name__))
    return value


def require_int(value, name, minimum=None):
    """An int on the wire is never a bool, at an API boundary as much as at a wire boundary."""
    if type(value) is not int:
        raise DomainError("%s must be an int, got %r" % (name, type(value).__name__))
    if minimum is not None and value < minimum:
        raise DomainError("%s must be >= %d, got %d" % (name, minimum, value))
    return value


def require_bool(value, name):
    if value is not True and value is not False:
        raise DomainError("%s must be a boolean, got %r" % (name, type(value).__name__))
    return value


def require_all(values, kind, name):
    if type(values) is not tuple:
        raise DomainError("%s must be a tuple, got %r" % (name, type(values).__name__))
    for item in values:
        require(item, kind, name + " item")
    return values


def member_of(kind, raw, field, reason):
    """Turn a wire value into a member of a closed domain, or refuse it.

    The DOMAIN of an enum is a semantic fact, so it belongs to the constructor that holds the
    field -- not to the parser, which would be a second authority (phase 1S Review A, A13). A
    member passes through unchanged so an internal caller can pass the enum it already holds.
    """
    from .closed import ConstructionError
    if not (isinstance(kind, type) and issubclass(kind, enum.Enum)):
        raise DomainError("member_of takes a closed domain, got %r" % (kind,))
    if type(raw) is kind:
        return raw
    for member in kind:
        if member.value == raw and type(raw) is type(member.value):
            return member
    raise ConstructionError(reason, field,
                            "one of %s, got %r" % ([m.value for m in kind], raw))
