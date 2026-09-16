"""Section 3 + 3a + B.3 - what remains to check once the shape is no longer in question.

Every field of a typed certificate is present, in domain and related to its neighbours as the
constructor requires. What a constructor cannot decide is what the fields mean TOGETHER as
EVIDENCE: accounting, impossible relations, conservation, the tombstone rule. Those produce a
CLASSIFICATION, not a refusal, because the contract says a record with an impossible relation is
read and marked UNVERIFIED rather than treated as unreadable.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .closed import Closed, ConstructionError
from .domains import (AcquisitionIntegrity, DomainError, Reason, SamplePolicy, require,
                      require_int)
from .records import (AcquisitionCertificate, CarrySweep, CarrySweepFailed, LOSS_COUNTERS,
                      SWEEP_TYPES)
from .values import Epoch

MAX_CLOCK_SKEW = 300
MIN_PLAUSIBLE_EPOCH = 1735689600

_LOSS_REASONS = frozenset()
LOSS_REASON = {"unreadable": Reason.SOURCE_UNREADABLE, "oversize": Reason.SOURCE_OVERSIZE,
               "malformed": Reason.LINE_UNPARSEABLE,
               "records_rejected": Reason.RECORD_SEMANTICALLY_INVALID,
               "identity_changed": Reason.SOURCE_IDENTITY_CHANGED,
               "not_attempted": Reason.SOURCE_NOT_ATTEMPTED,
               "dirs_unreadable": Reason.DISCOVERY_INCOMPLETE}
_LOSS_REASONS = frozenset(LOSS_REASON.values())


@dataclasses.dataclass(frozen=True, init=False)
class Evaluation(Closed):
    derived: AcquisitionIntegrity
    effective: AcquisitionIntegrity
    reasons: typing.Tuple[Reason, ...]
    loss_observed: bool
    asserted: typing.Union[AcquisitionIntegrity, Absence]

    def __repr__(self):
        return "Evaluation(%s/%s, %s)" % (self.derived.value, self.effective.value,
                                          [r.value for r in self.reasons])


def make_evaluation(derived, effective, reasons, loss_observed, asserted, field="evaluation"):
    """`effective` is DERIVED from the other two, so it cannot contradict them (Review A, A12)."""
    def need(ok, name, detail):
        if not ok:
            raise ConstructionError(Reason.CERT_BAD_TYPE, field + "." + name, detail)
    need(type(derived) is AcquisitionIntegrity, "derived", "an integrity state")
    need(type(effective) is AcquisitionIntegrity, "effective", "an integrity state")
    need(type(reasons) is tuple and all(type(r) is Reason for r in reasons), "reasons",
         "a tuple of reason codes")
    need(f.is_bool(loss_observed), "loss_observed", "exactly true or false")
    need(type(asserted) is AcquisitionIntegrity or type(asserted) is Absence, "asserted",
         "an integrity state, or an absence")
    expected = (derived if type(asserted) is Absence
                else AcquisitionIntegrity.worst(asserted, derived))
    need(effective is expected, "effective",
         "the effective state is worst(asserted, derived) = %s, not %s"
         % (expected.value, effective.value))
    need((not reasons) or derived is AcquisitionIntegrity.UNVERIFIED
         or all(r in _LOSS_REASONS for r in reasons), "reasons",
         "a state better than UNVERIFIED carries only loss reasons")
    return Evaluation._seal(derived=derived, effective=effective, reasons=reasons,
                            loss_observed=loss_observed, asserted=asserted)


def has_loss(certificate):
    require(certificate, AcquisitionCertificate, "certificate")
    return any(getattr(certificate, name) for name in LOSS_COUNTERS)


def accounting_ok(certificate, parsed):
    """Section 3a: every selected source has exactly one outcome, and selection balances."""
    require(certificate, AcquisitionCertificate, "certificate")
    require_int(parsed, "parsed", 0)
    outcomes = (parsed + certificate.unreadable + certificate.oversize
                + certificate.identity_changed + certificate.empty_source
                + certificate.not_attempted)
    if outcomes != certificate.selected:
        return False
    return certificate.selected + certificate.skipped_by_limit == certificate.discovered


def evaluate_observation(record, now):
    """The derived and effective integrity of one typed observation."""
    if type(record) not in SWEEP_TYPES:
        raise DomainError("evaluate_observation takes a validated sweep, got %r"
                          % type(record).__name__)
    require(now, Epoch, "now")
    cert, payload = record.certificate, record.payload
    reasons = []

    def add(code):
        if code not in reasons:
            reasons.append(code)

    parsed = len(payload.sample_manifest)
    if not accounting_ok(cert, parsed):
        add(Reason.CERT_ACCOUNTING_VIOLATION)

    if cert.sample_policy is SamplePolicy.ALL:
        if type(cert.sample_bound) is int or cert.skipped_by_limit:
            add(Reason.CERT_IMPOSSIBLE_RELATION)
    else:
        if type(cert.sample_bound) is not int or cert.selected > cert.sample_bound:
            add(Reason.CERT_IMPOSSIBLE_RELATION)
    for stamp in (cert.completed_at, payload.ts):
        if stamp.seconds > now.seconds + MAX_CLOCK_SKEW or stamp.seconds < MIN_PLAUSIBLE_EPOCH:
            add(Reason.CERT_IMPOSSIBLE_RELATION)

    selected_paths = {s.path for s in cert.frozen_selection}
    if any(e.path not in selected_paths for e in payload.sample_manifest):
        add(Reason.MANIFEST_NOT_SUBSET)

    if not payload.shares.is_empty and parsed == 0:
        add(Reason.CERT_CONSERVATION_VIOLATION)
    for value in (payload.sessions, payload.turns, payload.carry_bytes):
        if value > 0 and parsed == 0:
            add(Reason.CERT_CONSERVATION_VIOLATION)
    if not payload.shares.is_empty and (payload.turns == 0 or payload.carry_bytes == 0):
        add(Reason.CERT_CONSERVATION_VIOLATION)
    if payload.bpt > 0 and payload.turns == 0:
        add(Reason.CERT_CONSERVATION_VIOLATION)

    if type(record) is CarrySweepFailed:
        # section 5: the tombstone variant is its own TYPE, so this branch cannot be reached by
        # a record that merely claims to be one
        if not payload.shares.is_empty:
            add(Reason.CERT_CONSERVATION_VIOLATION)
        if parsed != 0:
            add(Reason.TOMBSTONE_INCONSISTENT)
        if any(v != 0 for v in (payload.sessions, payload.turns, payload.carry_bytes,
                                payload.bpt)):
            add(Reason.TOMBSTONE_INCONSISTENT)

    loss = has_loss(cert)
    if reasons:
        return make_evaluation(AcquisitionIntegrity.UNVERIFIED, AcquisitionIntegrity.UNVERIFIED,
                               tuple(reasons), loss, cert.asserted_integrity)

    derived = _derive(cert, parsed, reasons)
    asserted = cert.asserted_integrity
    effective = (derived if type(asserted) is Absence
                 else AcquisitionIntegrity.worst(asserted, derived))
    return make_evaluation(derived, effective, tuple(reasons), loss, asserted)


def _derive(cert, parsed, reasons):
    for name in LOSS_COUNTERS:
        if getattr(cert, name):
            reasons.append(LOSS_REASON[name])
    if parsed == 0 and (cert.selected - cert.not_attempted) > 0:
        return AcquisitionIntegrity.FAILED
    if has_loss(cert):
        return AcquisitionIntegrity.DEGRADED
    if cert.skipped_by_limit > 0:
        return AcquisitionIntegrity.BOUNDED
    return AcquisitionIntegrity.INTACT
