"""The world snapshot: what is true NOW, with absence spelled out and one constructor.

The three-state model of phase 1R survives unchanged -- it was the part that worked. What changed
is that the relationship between an absence STATE and a value is established here, once, so
`PRESENT` with no value and `KNOWN_ABSENT` carrying one are not expressible.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .canon import CanonMap
from .closed import Closed, ConstructionError
from .domains import AcquisitionIntegrity, ContainerIntegrity, Reason, member_of
from .values import (CandidateId, Digest, FindingId, NamedCounts, OrderKey, SampleId, ScopeId,
                     WorkloadId, WorldId, WorldIdCore, seq_canon)

WORLD_SCHEMA_VERSION = 1


def _require(ok, reason, field, detail):
    if not ok:
        raise ConstructionError(reason, field, detail)


def _maybe(value, kind, reason, field):
    """PRESENT(validated) | KNOWN_ABSENT | UNVERIFIED, and nothing else. Never None."""
    _require(type(value) is kind or type(value) is Absence, reason, field,
             "a validated %s, KNOWN_ABSENT or UNVERIFIED" % kind.__name__)
    return value


@dataclasses.dataclass(frozen=True, init=False)
class LiveSweepBinding(Closed):
    sample: SampleId
    sample_manifest: Digest
    certificate: Digest

    def canon(self):
        return CanonMap([("sample_id", self.sample.hex),
                         ("sample_manifest_digest", self.sample_manifest.hex),
                         ("certificate_digest", self.certificate.hex)])


@dataclasses.dataclass(frozen=True, init=False)
class LedgerState(Closed):
    binding: Digest
    integrity: ContainerIntegrity

    def canon(self):
        return CanonMap([("ledger_binding", self.binding.hex),
                         ("integrity", self.integrity.value)])


@dataclasses.dataclass(frozen=True, init=False)
class WorldObservation(Closed):
    order: OrderKey
    equivalence: Digest
    conflicted: bool
    quarantined: bool

    @property
    def run_id(self):
        return self.order.run_id

    def canon(self):
        return CanonMap([("order_key", self.order.canon()),
                         ("equivalence_digest", self.equivalence.hex),
                         ("conflicted", self.conflicted), ("quarantined", self.quarantined)])


@dataclasses.dataclass(frozen=True, init=False)
class WorldSnapshot(Closed):
    scope: ScopeId
    workload: WorkloadId
    finding: FindingId
    candidate: CandidateId
    world_id_core: WorldIdCore
    world_id: typing.Union[WorldId, Absence]
    history_integrity: ContainerIntegrity
    acquisition_integrity: typing.Union[AcquisitionIntegrity, Absence]
    ledger: typing.Union[LedgerState, Absence]
    live_sweep: typing.Union[LiveSweepBinding, Absence]
    newest_promotable: typing.Union[OrderKey, Absence]
    observations: typing.Tuple[WorldObservation, ...]
    metrics: NamedCounts

    def observation_for(self, run_id):
        for observation in self.observations:
            if observation.run_id == run_id:
                return observation
        return Absence.KNOWN_ABSENT

    def canon(self):
        return CanonMap([("world_schema", WORLD_SCHEMA_VERSION), ("scope_id", self.scope.text),
                         ("workload_class", self.workload.text),
                         ("observations", seq_canon(self.observations))])


@dataclasses.dataclass(frozen=True, init=False)
class ArtifactFileFacts(Closed):
    """Facts about the artifact FILE, which are not facts about the evidence."""
    readable: bool
    links: int
    size_ok: bool


def make_live_sweep_binding(sample, sample_manifest, certificate, field="live_sweep"):
    R = Reason.CERT_BAD_TYPE
    _require(type(sample) is SampleId, R, field + ".sample_id", "a validated SampleId")
    _require(type(sample_manifest) is Digest, R, field + ".sample_manifest_digest",
             "a validated Digest")
    _require(type(certificate) is Digest, R, field + ".certificate_digest",
             "a validated Digest")
    return LiveSweepBinding._seal(sample=sample, sample_manifest=sample_manifest,
                                  certificate=certificate)


def make_ledger_state(binding, integrity, field="ledger"):
    R = Reason.LEDGER_BAD_TYPE
    _require(type(binding) is Digest, R, field + ".ledger_binding", "a validated Digest")
    integrity = member_of(ContainerIntegrity, integrity, field + ".integrity", R)
    return LedgerState._seal(binding=binding, integrity=integrity)


def make_world_observation(order, equivalence, conflicted, quarantined,
                           field="world observation"):
    R = Reason.WORLD_UNVERIFIED
    _require(type(order) is OrderKey, R, field + ".order_key", "a validated OrderKey")
    _require(type(equivalence) is Digest, R, field + ".equivalence_digest",
             "a validated Digest")
    _require(f.is_bool(conflicted), R, field + ".conflicted", "exactly true or false")
    _require(f.is_bool(quarantined), R, field + ".quarantined", "exactly true or false")
    return WorldObservation._seal(order=order, equivalence=equivalence, conflicted=conflicted,
                                  quarantined=quarantined)


def make_world_snapshot(scope, workload, finding, candidate, world_id_core, world_id,
                        history_integrity, acquisition_integrity, ledger, live_sweep,
                        newest_promotable, observations, metrics, field="world"):
    R = Reason.WORLD_UNVERIFIED
    _require(type(scope) is ScopeId, R, field + ".scope_id", "a validated ScopeId")
    _require(type(workload) is WorkloadId, R, field + ".workload_class",
             "a validated WorkloadId")
    _require(type(finding) is FindingId, R, field + ".finding_id", "a registered FindingId")
    _require(type(candidate) is CandidateId, R, field + ".candidate_id",
             "a validated CandidateId")
    _require(type(world_id_core) is WorldIdCore, R, field + ".world_id_core",
             "a validated WorldIdCore")
    _maybe(world_id, WorldId, R, field + ".world_id")
    history_integrity = member_of(ContainerIntegrity, history_integrity,
                                  field + ".history_integrity", R)
    if type(acquisition_integrity) is not Absence:
        acquisition_integrity = member_of(AcquisitionIntegrity, acquisition_integrity,
                                          field + ".acquisition_integrity", R)
    _maybe(ledger, LedgerState, R, field + ".ledger")
    _maybe(live_sweep, LiveSweepBinding, R, field + ".live_sweep")
    _maybe(newest_promotable, OrderKey, R, field + ".newest_promotable")
    _require(type(observations) is tuple, R, field + ".observations", "a tuple")
    # a world holds each observation once. Which ORDER the caller listed them in is not evidence,
    # so the snapshot keeps them in canonical position order.
    positions, identities = set(), set()
    for observation in observations:
        _require(type(observation) is WorldObservation, R, field + ".observations",
                 "a validated WorldObservation")
        key = observation.order._sort()
        _require(key not in positions, R, field + ".observations",
                 "two observations at one position")
        _require(observation.run_id.text not in identities, R, field + ".observations",
                 "one observation supports a world once, got %r twice"
                 % observation.run_id.text)
        positions.add(key)
        identities.add(observation.run_id.text)
    _require(type(metrics) is NamedCounts, R, field + ".metrics", "validated NamedCounts")
    return WorldSnapshot._seal(
        scope=scope, workload=workload, finding=finding, candidate=candidate,
        world_id_core=world_id_core, world_id=world_id, history_integrity=history_integrity,
        acquisition_integrity=acquisition_integrity, ledger=ledger, live_sweep=live_sweep,
        newest_promotable=newest_promotable,
        observations=tuple(sorted(observations, key=lambda o: o.order._sort())),
        metrics=metrics)


def make_file_facts(readable, links, size_ok, field="file_facts"):
    R = Reason.ARTIFACT_UNREADABLE
    _require(f.is_bool(readable), R, field + ".readable", "exactly true or false")
    _require(f.is_nat(links), R, field + ".links", "a non-negative int")
    _require(f.is_bool(size_ok), R, field + ".size_ok", "exactly true or false")
    return ArtifactFileFacts._seal(readable=readable, links=links, size_ok=size_ok)
