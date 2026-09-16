"""Sections 2a, 3b, 9a, 9b - the population, the world, the floors and the run status.

The run-level inputs used to be lists of raw mappings, which is how a finding with a misspelled
persistence value reached an invariant check. They are typed here too: a finding outcome is a
type, and its states are enums.

Section 2a used to compute a TEMPORAL WINDOW: the records of the last N days, selected by the
kernel. That is gone. An analysis now rests on an explicit POPULATION -- the validated
observations of one scope and one workload, carrying its own identity -- and a caller that wants
less evidence acquires less evidence, which its certificates then record as BOUNDED. The kernel
performs no temporal selection of its own, so no two callers can disagree about which records a
container's integrity was computed over.
"""
import dataclasses
import typing

from .absence import Absence
from .domains import (AnalysisSufficiency, DomainError, FindingState, IneligibleReason, Reason,
                      Persistence, RunStatus, WorldState, member_of, require,
                      require_all, require_bool)
from .identity import canonical_order, certificate_world_id, population_id
from . import forms as f
from .closed import Closed, ConstructionError
from .records import SWEEP_TYPES, ValidatedContainer
from .registry import floors_for
from .values import Digest, FindingId, ScopeId, WorkloadId


@dataclasses.dataclass(frozen=True, init=False)
class Population(Closed):
    """The observations an analysis rests on, and the identity of that exact set.

    It is a SET of validated observations, not a time span: it names its scope, its workload and
    its members, and its identity is a digest over what those members say. Two runs that read
    the same evidence produce the same population identity; a run that read different evidence
    cannot pretend otherwise.
    """
    scope: ScopeId
    workload: WorkloadId
    members: typing.Tuple[object, ...]
    identity: Digest

    @property
    def size(self):
        return len(self.members)

    @property
    def empty(self):
        return not self.members


@dataclasses.dataclass(frozen=True, init=False)
class SufficiencyFacts(Closed):
    """Section 3b inputs. Every floor input is a named, typed fact, not a mapping lookup."""
    sessions: int
    turns: int
    carry_bytes: int
    shares_non_empty: bool
    ledger_writes: int
    ledger_days: int
    comparable_records: int
    population_truncated_by_rotation: bool


@dataclasses.dataclass(frozen=True, init=False)
class FindingOutcome(Closed):
    finding: FindingId
    state: FindingState
    persistence: Persistence
    ineligible: typing.Union[IneligibleReason, Absence]


@dataclasses.dataclass(frozen=True, init=False)
class RunOutcome(Closed):
    status: RunStatus
    artifacts_written: typing.Tuple[FindingId, ...]

    @property
    def exit_code(self):
        return self.status.exit_code

    @property
    def artifacts_written_count(self):
        return len(self.artifacts_written)


def _need(ok, field, detail):
    """Construction refusals speak one language: ConstructionError, with a reason and a field."""
    if not ok:
        raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field, detail)


def make_population(scope, workload, members, field="population"):
    """The ONE constructor. It establishes the relations a population cannot be without."""
    _need(type(scope) is ScopeId, field + ".scope", "a validated ScopeId")
    _need(type(workload) is WorkloadId, field + ".workload", "a validated WorkloadId")
    _need(type(members) is tuple and all(type(m) in SWEEP_TYPES for m in members),
          field + ".members", "a tuple of validated sweeps")
    _need(all(m.envelope.scope == scope for m in members), field + ".members",
          "every member observes the population's scope")
    _need(all(m.certificate.workload == workload for m in members), field + ".members",
          "every member observes the population's workload class")
    _need(members == canonical_order(members), field + ".members",
          "members are held in canonical order, so a permuted batch reads the same")
    keys = [(m.envelope.order, m.equivalence()) for m in members]
    _need(len(set(keys)) == len(keys), field + ".members",
          "one entry per OBSERVATION: B.4 says an exact repeat at one position is a RETRY of "
          "the same observation, and counting it twice would inflate every count floor")
    return Population._seal(scope=scope, workload=workload, members=members,
                            identity=population_id(scope, workload, members))


def make_sufficiency_facts(sessions, turns, carry_bytes, shares_non_empty, ledger_writes,
                           ledger_days, comparable_records, population_truncated_by_rotation,
                           field="sufficiency_facts"):
    values = {"sessions": sessions, "turns": turns, "carry_bytes": carry_bytes,
              "ledger_writes": ledger_writes, "ledger_days": ledger_days,
              "comparable_records": comparable_records}
    for name, value in values.items():
        _need(f.is_nat(value), field + "." + name, "a non-negative int")
    for name, value in (("shares_non_empty", shares_non_empty),
                        ("population_truncated_by_rotation", population_truncated_by_rotation)):
        _need(f.is_bool(value), field + "." + name, "exactly true or false")
    return SufficiencyFacts._seal(shares_non_empty=shares_non_empty,
                                  population_truncated_by_rotation=population_truncated_by_rotation,
                                  **values)


def make_finding_outcome(finding, state, persistence, ineligible, field="finding_outcome"):
    """Invariant I3 is a relation between two of these fields, so it lives here (Review A, A10)."""
    _need(type(finding) is FindingId, field + ".finding", "a registered FindingId")
    state = member_of(FindingState, state, field + ".state", Reason.RECORD_SHAPE_INVALID)
    persistence = member_of(Persistence, persistence, field + ".persistence",
                            Reason.RECORD_SHAPE_INVALID)
    _need(type(ineligible) is IneligibleReason or type(ineligible) is Absence,
          field + ".ineligible", "an ineligible reason, or an absence")
    _need(state is FindingState.ELIGIBLE or persistence is Persistence.NOT_ATTEMPTED,
          field + ".persistence",
          "I3: a finding that is not ELIGIBLE was not attempted, got %s + %s"
          % (state.value, persistence.value))
    _need((type(ineligible) is Absence) or state is not FindingState.ELIGIBLE
          or persistence is Persistence.NOT_ATTEMPTED, field + ".ineligible",
          "an ELIGIBLE finding that was attempted has no ineligible reason")
    return FindingOutcome._seal(finding=finding, state=state, persistence=persistence,
                                ineligible=ineligible)


def make_run_outcome(status, artifacts_written, field="run_outcome"):
    """I2 and I6 are relations between the status and the artifact list (Review A, A11)."""
    _need(type(status) is RunStatus, field + ".status", "a run status")
    _need(type(artifacts_written) is tuple
          and all(type(a) is FindingId for a in artifacts_written),
          field + ".artifacts_written", "a tuple of FindingId")
    names = [a.text for a in artifacts_written]
    _need(len(set(names)) == len(names), field + ".artifacts_written",
          "one entry per finding")
    _need(status.writes_artifacts or not artifacts_written, field + ".artifacts_written",
          "I2: %s writes no artifact, so it may not name one" % status.value[0])
    return RunOutcome._seal(status=status, artifacts_written=artifacts_written)


def population_for(container, scope, workload):
    """Every validated observation this container holds for one scope and one workload.

    No cutoff, no horizon, no "newest N": the kernel does not choose which evidence counts. A
    caller that wants a smaller population acquires one, and the acquisition certificate records
    that it was BOUNDED -- which the promotion gate then requires the operator to accept.

    Canonical order (position, then record digest) so a permuted read produces the same
    population and therefore the same identity.
    """
    if not isinstance(container, ValidatedContainer):
        raise DomainError("population_for takes a ValidatedContainer, got %r"
                          % type(container).__name__)
    if not isinstance(scope, ScopeId) or not isinstance(workload, WorkloadId):
        raise DomainError("scope and workload are validated labels")
    seen = {}
    for record in container.sweeps(scope):
        if record.certificate.workload != workload:
            continue
        # B.4: one position, one identical content, one observation -- written twice by the
        # crash-recovery path the contract prescribes. `dedup` says the same thing about the
        # same pair; a population that counted both would contradict it.
        seen.setdefault((record.envelope.order, record.equivalence()), record)
    return make_population(scope, workload, canonical_order(tuple(seen.values())))


def world_state(members, scope):
    """One world, or more than one? Recomputed from each certificate's own preimages."""
    if type(members) is not tuple or any(type(m) not in SWEEP_TYPES for m in members):
        raise DomainError("population members are validated sweeps")
    require(scope, ScopeId, "scope")
    worlds = {certificate_world_id(m.certificate, scope) for m in members}
    return WorldState.MIXED_WORLD if len(worlds) > 1 else WorldState.SINGLE_WORLD


def sufficiency(finding, facts):
    """Section 3b - evaluated against the floors this finding's `consumes` implies."""
    if not isinstance(finding, FindingId):
        raise DomainError("sufficiency takes a FindingId, got %r" % type(finding).__name__)
    if not isinstance(facts, SufficiencyFacts):
        raise DomainError("sufficiency takes SufficiencyFacts, got %r" % type(facts).__name__)
    spec = floors_for(finding.text)
    if facts.population_truncated_by_rotation:
        return AnalysisSufficiency.INSUFFICIENT
    if spec.sampled:
        if facts.sessions < spec.min_sessions or facts.turns < spec.min_turns:
            return AnalysisSufficiency.INSUFFICIENT
        if facts.shares_non_empty and facts.carry_bytes == 0:
            return AnalysisSufficiency.INSUFFICIENT
    if spec.uses_ledger:
        if facts.ledger_writes < spec.min_ledger_writes:
            return AnalysisSufficiency.INSUFFICIENT
        if facts.ledger_days < spec.min_ledger_days:
            return AnalysisSufficiency.INSUFFICIENT
    if spec.min_history_for_trend > 0 and facts.comparable_records < spec.min_history_for_trend:
        return AnalysisSufficiency.INSUFFICIENT
    return AnalysisSufficiency.SUFFICIENT


def run_status(findings, observation_append_failed=False):
    """Section 9a - the FIRST matching row, with failure outranking success."""
    require_all(tuple(findings) if type(findings) in (list, tuple) else findings,
                FindingOutcome, "findings")
    require_bool(observation_append_failed, "observation_append_failed")
    written = tuple(f.finding for f in findings if f.persistence is Persistence.WRITTEN)
    reasons = [f.ineligible for f in findings]
    persistences = [f.persistence for f in findings]

    if observation_append_failed:
        status = RunStatus.OBSERVATION_LOST
    elif Persistence.FAILED in persistences:
        status = RunStatus.EMISSION_FAILED
    elif Persistence.REFUSED in persistences:
        status = RunStatus.CANDIDATE_REVIEW_REQUIRED
    elif any(p in (Persistence.WRITTEN, Persistence.ALREADY_CURRENT) for p in persistences):
        status = RunStatus.CANDIDATE
    elif any(isinstance(r, IneligibleReason) and r.is_evidence_failure for r in reasons):
        status = RunStatus.DEGRADED_EVIDENCE
    elif IneligibleReason.BOUNDED_UNACCEPTED in reasons:
        status = RunStatus.BOUNDED_EVIDENCE
    elif IneligibleReason.INSUFFICIENT in reasons:
        status = RunStatus.INSUFFICIENT_DATA
    else:
        status = RunStatus.NO_ACTION
    if not status.writes_artifacts:
        written = ()
    return make_run_outcome(status, written)


def check_invariants(findings, outcome):
    """I1..I7, mechanically. Returns the violated invariant names."""
    if type(outcome) is not RunOutcome:
        raise DomainError("check_invariants takes a RunOutcome")
    require_all(tuple(findings) if type(findings) in (list, tuple) else findings,
                FindingOutcome, "findings")
    bad = []
    persistences = [f.persistence for f in findings]
    promoted = any(p in (Persistence.WRITTEN, Persistence.ALREADY_CURRENT) for p in persistences)
    blocked = any(p in (Persistence.FAILED, Persistence.REFUSED) for p in persistences)
    if (outcome.status is RunStatus.CANDIDATE) != (promoted and not blocked):
        bad.append("I1")
    if not outcome.status.writes_artifacts and outcome.artifacts_written_count != 0:
        bad.append("I2")
    for f in findings:
        if f.state is not FindingState.ELIGIBLE and f.persistence is not Persistence.NOT_ATTEMPTED:
            bad.append("I3")
            break
    expected = sorted(f.finding.text for f in findings if f.persistence is Persistence.WRITTEN)
    if outcome.status.writes_artifacts and \
            sorted(f.text for f in outcome.artifacts_written) != expected:
        bad.append("I6")
    if outcome.status is RunStatus.OBSERVATION_LOST and promoted:
        bad.append("I7")
    return bad
