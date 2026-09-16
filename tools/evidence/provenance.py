"""Section 11 artifact provenance: two manifest types, one constructor each.

The split that worked in phase 1R is kept: a sampled finding carries a WorldId and rests on at
least one observation, a ledger-only finding carries a WorldIdCore. Neither can present the
other's identity, because the field types differ.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .canon import CanonMap
from .closed import Closed, ConstructionError
from .domains import AcquisitionIntegrity, AnalysisSufficiency, Reason, member_of
from .values import (CandidateId, Digest, FindingId, NamedCounts, OrderKey, ScopeId, WorkloadId,
                     WorldId, WorldIdCore, digest_of, seq_canon)
from .world import LiveSweepBinding

ARTIFACT_SCHEMA_VERSION = 2
MANIFEST_SCHEMA_VERSION = 2


def _require(ok, reason, field, detail):
    if not ok:
        raise ConstructionError(reason, field, detail)


@dataclasses.dataclass(frozen=True, init=False)
class ObservationRef(Closed):
    order: OrderKey
    equivalence: Digest

    @property
    def run_id(self):
        return self.order.run_id

    def canon(self):
        return CanonMap([("order_key", self.order.canon()),
                         ("equivalence_digest", self.equivalence.hex)])


@dataclasses.dataclass(frozen=True, init=False)
class SampledManifest(Closed):
    world: WorldId
    observations: typing.Tuple[ObservationRef, ...]
    ledger: typing.Union[Digest, Absence]
    live_sweep: typing.Union[LiveSweepBinding, Absence]
    metrics: NamedCounts

    @property
    def created_at(self):
        return self.observations[-1].order

    def canon(self):
        ledger = self.ledger.hex if type(self.ledger) is Digest else None
        live = self.live_sweep.canon() if type(self.live_sweep) is LiveSweepBinding else None
        return CanonMap([("manifest_schema", MANIFEST_SCHEMA_VERSION), ("kind", "sampled"),
                         ("world_id", self.world.hex),
                         ("observations", seq_canon(self.observations)),
                         ("ledger_binding", ledger), ("live_sweep", live),
                         ("metrics", self.metrics.canon())])


@dataclasses.dataclass(frozen=True, init=False)
class LedgerOnlyManifest(Closed):
    world_core: WorldIdCore
    ledger: Digest
    metrics: NamedCounts

    @property
    def created_at(self):
        return Absence.KNOWN_ABSENT

    def canon(self):
        return CanonMap([("manifest_schema", MANIFEST_SCHEMA_VERSION), ("kind", "ledger_only"),
                         ("world_id_core", self.world_core.hex),
                         ("ledger_binding", self.ledger.hex),
                         ("metrics", self.metrics.canon())])


@dataclasses.dataclass(frozen=True, init=False)
class ArtifactProvenance(Closed):
    candidate: CandidateId
    finding: FindingId
    scope: ScopeId
    workload: WorkloadId
    acquisition: AcquisitionIntegrity
    sufficiency: AnalysisSufficiency
    created_by_version: str
    manifest: typing.Union[SampledManifest, LedgerOnlyManifest]

    @property
    def accepts_bounded(self):
        return self.acquisition is AcquisitionIntegrity.BOUNDED

    @property
    def created_at(self):
        return self.manifest.created_at

    @property
    def evidence_binding(self):
        return digest_of(self.manifest)

    def canon(self):
        return CanonMap([("artifact_schema", ARTIFACT_SCHEMA_VERSION),
                         ("candidate_id", self.candidate.text),
                         ("finding_id", self.finding.text), ("scope_id", self.scope.text),
                         ("workload_class", self.workload.text),
                         ("acquisition_integrity", self.acquisition.value),
                         ("analysis_sufficiency", self.sufficiency.value),
                         ("created_by_version", self.created_by_version),
                         ("evidence_manifest", self.manifest.canon())])


ART = Reason.ARTIFACT_INTERNAL_MISMATCH


def make_observation_ref(order, equivalence, field="observation"):
    _require(type(order) is OrderKey, ART, field + ".order_key", "a validated OrderKey")
    _require(type(equivalence) is Digest, ART, field + ".equivalence_digest",
             "a validated Digest")
    return ObservationRef._seal(order=order, equivalence=equivalence)


def make_sampled_manifest(world, observations, ledger, live_sweep, metrics,
                          field="evidence_manifest"):
    _require(type(world) is WorldId, ART, field + ".world_id",
             "a sampled finding carries the SAMPLED world identity")
    _require(type(observations) is tuple and observations, ART, field + ".observations",
             "a sampled manifest rests on at least one observation")
    previous, identities = None, set()
    for ref in observations:
        _require(type(ref) is ObservationRef, ART, field + ".observations",
                 "a validated ObservationRef")
        # A.5's manifest form is sorted by order_key, and one observation supports a finding once
        _require(previous is None or previous < ref.order._sort(), ART,
                 field + ".observations", "carried in canonical position order")
        _require(ref.run_id.text not in identities, ART, field + ".observations",
                 "one observation supports an artifact once, got %r twice" % ref.run_id.text)
        previous = ref.order._sort()
        identities.add(ref.run_id.text)
    _require(type(ledger) is Digest or ledger is Absence.KNOWN_ABSENT, ART,
             field + ".ledger_binding", "a validated Digest, or KNOWN_ABSENT")
    _require(type(live_sweep) is LiveSweepBinding or live_sweep is Absence.KNOWN_ABSENT, ART,
             field + ".live_sweep", "a validated LiveSweepBinding, or KNOWN_ABSENT")
    _require(type(metrics) is NamedCounts, ART, field + ".metrics", "validated NamedCounts")
    return SampledManifest._seal(world=world, observations=observations, ledger=ledger,
                                 live_sweep=live_sweep, metrics=metrics)


def make_ledger_only_manifest(world_core, ledger, metrics, field="evidence_manifest"):
    _require(type(world_core) is WorldIdCore, ART, field + ".world_id_core",
             "a ledger-only finding carries the world CORE, with no sampling dimension")
    _require(type(ledger) is Digest, ART, field + ".ledger_binding", "a validated Digest")
    _require(type(metrics) is NamedCounts, ART, field + ".metrics", "validated NamedCounts")
    return LedgerOnlyManifest._seal(world_core=world_core, ledger=ledger, metrics=metrics)


def make_provenance(candidate, finding, scope, workload, acquisition, sufficiency,
                    created_by_version, manifest, field="artifact"):
    _require(type(candidate) is CandidateId, ART, field + ".candidate_id",
             "a validated CandidateId")
    _require(type(finding) is FindingId, ART, field + ".finding_id", "a registered FindingId")
    _require(type(scope) is ScopeId, ART, field + ".scope_id", "a validated ScopeId")
    _require(type(workload) is WorkloadId, ART, field + ".workload_class",
             "a validated WorkloadId")
    acquisition = member_of(AcquisitionIntegrity, acquisition,
                            field + ".acquisition_integrity", ART)
    sufficiency = member_of(AnalysisSufficiency, sufficiency,
                            field + ".analysis_sufficiency", ART)
    _require(f.is_str(created_by_version), ART, field + ".created_by_version", "a string")
    _require(type(manifest) in (SampledManifest, LedgerOnlyManifest), ART,
             field + ".evidence_manifest", "a validated manifest of one of the two kinds")
    return ArtifactProvenance._seal(candidate=candidate, finding=finding, scope=scope,
                                    workload=workload, acquisition=acquisition,
                                    sufficiency=sufficiency,
                                    created_by_version=created_by_version, manifest=manifest)
