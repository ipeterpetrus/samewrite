"""Appendix B.1 - the finding registry, as typed floors AND an explicit dependency contract.

A floor that can be read with `spec.get("min_turns", 0)` is a floor that can silently be zero.
Each entry is a frozen object here, so a floor that does not apply is not merely missing: the
entry says which evidence sources the finding consumes, and a floor outside that set is a
registry error at import time.

WHAT THE SCOPE CUTS CHANGED. Two findings are gone. `carry_bytes_trend` went with the temporal
window; `carry_share_concentration` went with the host-shift gate, because it was the only
retained finding that aggregated across the observations of a population and therefore the only
one whose validity depended on those observations being comparable across hosts. No entry in this
table consumes `history` any more: every retained finding rests on ONE observation (a live sweep)
or ONE certificate (the ledger), which is why "same host" has no referent for either of them.

Entries used to carry `horizon_days`: the width of the
temporal window the kernel selected for that finding. There is no kernel-side temporal selection
any more, so the field is gone -- not defaulted, not ignored, gone -- and a finding whose
validity rested on it is not in this table at all. What each entry gained instead is the rest of
its dependency contract, stated mechanically rather than left to the caller to remember: the
container integrity it needs, the acquisition states it can rest on, the sufficiency it needs,
and the dimensions along which two observations are comparable.
"""
import dataclasses
import typing

from .closed import Closed, ConstructionError
from .domains import AcquisitionIntegrity, AnalysisSufficiency, ContainerIntegrity, Reason

MAX_CLOCK_SKEW = 300
MIN_PLAUSIBLE_EPOCH = 1735689600
MIN_HISTORY_FOR_TREND_FLOOR = 5
EVIDENCE_SOURCES = ("live_sweep", "history", "ledger")
COMPARABILITY_DIMENSIONS = ("scope", "workload", "world")
# a promotion can rest on evidence that was whole, or on evidence that was deliberately bounded
# and explicitly accepted -- and on nothing else
PROMOTABLE_ACQUISITION = (AcquisitionIntegrity.INTACT, AcquisitionIntegrity.BOUNDED)


class RegistryError(ValueError):
    """A finding with no entry, or an entry that cannot be evaluated."""


@dataclasses.dataclass(frozen=True)
class Floors(object):
    """Not minted: this is a constant of the program, not a decoded wire value."""
    consumes: typing.Tuple[str, ...]
    min_history_for_trend: int
    requires_container: ContainerIntegrity
    requires_acquisition: typing.Tuple[AcquisitionIntegrity, ...]
    requires_sufficiency: AnalysisSufficiency
    comparability: typing.Tuple[str, ...]
    min_sessions: int = 0
    min_turns: int = 0
    min_ledger_writes: int = 0
    min_ledger_days: int = 0

    @property
    def sampled(self):
        return any(c in ("live_sweep", "history") for c in self.consumes)

    @property
    def uses_ledger(self):
        return "ledger" in self.consumes

    @property
    def uses_history(self):
        return "history" in self.consumes


FINDING_FLOORS = {
    "listing_cost": Floors(
        consumes=("live_sweep",), min_history_for_trend=0,
        requires_container=ContainerIntegrity.INTACT,
        requires_acquisition=PROMOTABLE_ACQUISITION,
        requires_sufficiency=AnalysisSufficiency.SUFFICIENT,
        comparability=("scope", "workload", "world"),
        min_sessions=10, min_turns=50),
    # the ledger certificate carries its own span; the kernel selects nothing
    "write_guard_retirement": Floors(
        consumes=("ledger",), min_history_for_trend=0,
        requires_container=ContainerIntegrity.INTACT,
        requires_acquisition=PROMOTABLE_ACQUISITION,
        requires_sufficiency=AnalysisSufficiency.SUFFICIENT,
        comparability=("scope", "workload", "world"),
        min_ledger_writes=500, min_ledger_days=30),
}

# Findings that were REMOVED with the temporal window, and why. Read by the unsupported-feature
# test: naming them here is how "we removed it" stays checkable instead of becoming folklore.
REMOVED_FINDINGS = {
    "carry_bytes_trend": "a trend over a 90-day window: its statement is temporal, and there is "
                         "no non-temporal redefinition of it that means the same thing",
    "carry_share_concentration":
        "it aggregated across the observations of a population, so its validity needed those "
        "observations to be COMPARABLE -- and with host-shift removed nothing establishes that "
        "two observations from different hosts are. The Owner cut the finding rather than add a "
        "host-comparability mechanism to preserve it; approximating it (ignore the host, newest "
        "host wins, majority host) would keep the name and change the meaning",
}


def validate_registry(floors):
    """Return a list of problems; an empty list means the registry may be imported."""
    if type(floors) is not dict:
        return ["a registry is a table of named floors, got %r" % type(floors).__name__]
    problems = []
    for name in sorted(floors):
        spec = floors[name]
        if not isinstance(spec, Floors):
            problems.append("%s: entry must be a Floors" % name)
            continue
        if not spec.consumes:
            problems.append("%s: consumes must be a non-empty list" % name)
        for source in spec.consumes:
            if source not in EVIDENCE_SOURCES:
                problems.append("%s: unknown evidence source %r" % (name, source))
        if spec.sampled:
            for key in ("min_sessions", "min_turns"):
                if getattr(spec, key) < 1:
                    problems.append("%s: %s must be an int >= 1" % (name, key))
        else:
            for key in ("min_sessions", "min_turns"):
                if getattr(spec, key):
                    problems.append("%s: %s can never be evaluated" % (name, key))
        if spec.uses_ledger:
            for key in ("min_ledger_writes", "min_ledger_days"):
                if getattr(spec, key) < 1:
                    problems.append("%s: %s must be an int >= 1" % (name, key))
        else:
            for key in ("min_ledger_writes", "min_ledger_days"):
                if getattr(spec, key):
                    problems.append("%s: %s can never be evaluated" % (name, key))
        if spec.min_history_for_trend < 0:
            problems.append("%s: min_history_for_trend must be an int >= 0" % name)
        elif 0 < spec.min_history_for_trend < MIN_HISTORY_FOR_TREND_FLOOR:
            problems.append("%s: min_history_for_trend below the floor" % name)
        # a floor outside the consumed set can never be evaluated, which the docstring has always
        # claimed and nothing enforced
        if spec.min_history_for_trend and not spec.uses_history:
            problems.append("%s: min_history_for_trend without consuming history" % name)
        # --- the rest of the dependency contract
        if not isinstance(spec.requires_container, ContainerIntegrity):
            problems.append("%s: requires_container must be a ContainerIntegrity" % name)
        if type(spec.requires_acquisition) is not tuple or not spec.requires_acquisition:
            problems.append("%s: requires_acquisition must be a non-empty tuple" % name)
        else:
            for state in spec.requires_acquisition:
                if not isinstance(state, AcquisitionIntegrity):
                    problems.append("%s: %r is not an AcquisitionIntegrity" % (name, state))
                elif state not in PROMOTABLE_ACQUISITION:
                    problems.append("%s: %s can never support a promotion"
                                    % (name, state.value))
            if AcquisitionIntegrity.INTACT not in spec.requires_acquisition:
                problems.append("%s: INTACT evidence must always be acceptable" % name)
        if spec.requires_sufficiency is not AnalysisSufficiency.SUFFICIENT:
            problems.append("%s: requires_sufficiency must be SUFFICIENT" % name)
        if type(spec.comparability) is not tuple or not spec.comparability:
            problems.append("%s: comparability must be a non-empty tuple" % name)
        else:
            for dimension in spec.comparability:
                if dimension not in COMPARABILITY_DIMENSIONS:
                    problems.append("%s: unknown comparability dimension %r" % (name, dimension))
        # the promotion gate refuses a mixed world for every finding, so every entry must SAY
        # so: a declaration that omits what is enforced is the mismatch Review A found (A2)
        if "world" not in spec.comparability:
            problems.append("%s: every finding is refused on a mixed world, so every entry "
                            "must declare the world dimension" % name)
    for name in sorted(floors):
        if name in REMOVED_FINDINGS:
            problems.append("%s: named both as retained and as removed" % name)
    return problems


def floors_for(finding_id):
    if type(finding_id) is not str:
        raise RegistryError("a finding id is a string, got %r" % type(finding_id).__name__)
    if finding_id in REMOVED_FINDINGS:
        raise RegistryError("%r is not supported in this generation: %s"
                            % (finding_id, REMOVED_FINDINGS[finding_id]))
    if finding_id not in FINDING_FLOORS:
        raise RegistryError("no registry entry for %r; a missing floor is never a default"
                            % finding_id)
    return FINDING_FLOORS[finding_id]


@dataclasses.dataclass(frozen=True, init=False)
class DependencyContract(Closed):
    """What one finding needs, as a TYPED value.

    It was a raw mapping for exactly one review round, and the promotion gate read it with
    `contract["container_integrity"]` -- a raw container inside the evidence package, which is
    the one thing this kernel forbids. A contract a consumer can misspell is not a contract.
    """
    finding: str
    evidence_components: typing.Tuple[str, ...]
    container_integrity: ContainerIntegrity
    acquisition_integrity: typing.Tuple[AcquisitionIntegrity, ...]
    sufficiency: AnalysisSufficiency
    comparability: typing.Tuple[str, ...]
    min_sessions: int
    min_turns: int
    min_history_for_trend: int
    min_ledger_writes: int
    min_ledger_days: int

    def needs(self, dimension):
        return dimension in self.comparability


def make_dependency_contract(finding, evidence_components, container_integrity,
                             acquisition_integrity, sufficiency, comparability, min_sessions,
                             min_turns, min_history_for_trend, min_ledger_writes,
                             min_ledger_days, field="dependency_contract"):
    """The ONE constructor: the registry is the only place a contract can come from."""
    def need(ok, name, detail):
        if not ok:
            raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field + "." + name, detail)

    need(type(finding) is str and finding in FINDING_FLOORS, "finding", "a retained finding")
    need(type(evidence_components) is tuple
         and all(c in EVIDENCE_SOURCES for c in evidence_components),
         "evidence_components", "evidence sources this kernel knows")
    need(isinstance(container_integrity, ContainerIntegrity), "container_integrity",
         "a ContainerIntegrity")
    need(type(acquisition_integrity) is tuple and acquisition_integrity
         and all(a in PROMOTABLE_ACQUISITION for a in acquisition_integrity),
         "acquisition_integrity", "acquisition states that can support a promotion")
    need(sufficiency is AnalysisSufficiency.SUFFICIENT, "sufficiency", "SUFFICIENT")
    need(type(comparability) is tuple and "world" in comparability
         and all(d in COMPARABILITY_DIMENSIONS for d in comparability),
         "comparability", "declared dimensions including the world")
    floors = (min_sessions, min_turns, min_history_for_trend, min_ledger_writes, min_ledger_days)
    need(all(type(v) is int and not isinstance(v, bool) and v >= 0 for v in floors),
         "floors", "non-negative ints")
    return DependencyContract._seal(
        finding=finding, evidence_components=evidence_components,
        container_integrity=container_integrity, acquisition_integrity=acquisition_integrity,
        sufficiency=sufficiency, comparability=comparability, min_sessions=min_sessions,
        min_turns=min_turns, min_history_for_trend=min_history_for_trend,
        min_ledger_writes=min_ledger_writes, min_ledger_days=min_ledger_days)


def dependency_contract(finding_id):
    """What this finding needs, as a typed value rather than a convention callers remember."""
    spec = floors_for(finding_id)
    return make_dependency_contract(
        finding_id, spec.consumes, spec.requires_container, spec.requires_acquisition,
        spec.requires_sufficiency, spec.comparability, spec.min_sessions, spec.min_turns,
        spec.min_history_for_trend, spec.min_ledger_writes, spec.min_ledger_days)


_problems = validate_registry(FINDING_FLOORS)
if _problems:                                    # an invalid registry must not import
    raise RegistryError("; ".join(_problems))
