"""Section 5 - failed observations are observations, and freshness reads the newest measurement."""
from .absence import Absence
from .certificate import evaluate_observation
from .domains import AcquisitionIntegrity, DomainError, require, require_bool
from .identity import canonical_newest
from .records import CarrySweep, SWEEP_TYPES, ValidatedContainer
from .values import Epoch, ScopeId

TOMBSTONE_TRIGGERS = ("permission_denied", "all_sources_unreadable", "parser_crash",
                      "zero_parsed_after_discovery", "timeout_before_any_parse",
                      "bounded_selection_failure")


def is_measurement(record):
    """Only a sweep carries a metric; every container event is evidence about the container."""
    return type(record) in SWEEP_TYPES


def newest_observation(container, scope):
    """The newest measurement in one scope, or KNOWN_ABSENT.

    Two records can sit at the same position -- one run, one sequence, written twice -- and an
    ordering that only asks `<` leaves the winner to whoever was read first, which made freshness
    depend on input order (Review B, B2). The rule is `identity.canonical_newest`, the same total
    order dedup uses, defined once.
    """
    require(container, ValidatedContainer, "container")
    require(scope, ScopeId, "scope")
    sweeps = container.sweeps(scope)
    if not sweeps:
        return Absence.KNOWN_ABSENT
    return canonical_newest(sweeps)


def freshness_ok(container, scope, now, bounded_accepted=False):
    """The newest MEASUREMENT must be promotable on its own terms, or the scope is not current."""
    require_bool(bounded_accepted, "bounded_accepted")
    if not isinstance(now, Epoch):
        raise DomainError("now is an Epoch, got %r" % type(now).__name__)
    newest = newest_observation(container, scope)
    if isinstance(newest, Absence):
        return False
    if type(newest) is not CarrySweep:
        return False
    state = evaluate_observation(newest, now=now).effective
    if state is AcquisitionIntegrity.INTACT:
        return True
    return state is AcquisitionIntegrity.BOUNDED and bounded_accepted
