"""Section 11 - artifact provenance bound to the evidence AS OF creation, over typed objects.

Two questions, kept apart because conflating them taught operators to ignore the state that also
means forged:
    INTEGRITY  is this artifact authentic for the evidence it names?
    FRESHNESS  has the world moved on since?

What changed in phase 1R is what the classifier no longer has to ask. It cannot ask whether the
header has a field, whether a value is the right type, or whether the world "has" a ledger:
a missing world fact is a different VALUE from an absent one, and a sampled manifest is a
different TYPE from a ledger-only one.
"""
import dataclasses
import typing

from .absence import Absence
from . import forms as f
from .closed import Closed, ConstructionError
from .domains import (AcquisitionIntegrity, AnalysisSufficiency, ArtifactClassification,
                      ContainerIntegrity, DomainError, Reason)
from .provenance import ArtifactProvenance, LedgerOnlyManifest, SampledManifest
from .values import Digest
from .world import ArtifactFileFacts, LedgerState, LiveSweepBinding, WorldSnapshot

PROMOTABLE = (AcquisitionIntegrity.INTACT, AcquisitionIntegrity.BOUNDED)


@dataclasses.dataclass(frozen=True, init=False)
class Classification(Closed):
    state: ArtifactClassification
    reasons: typing.Tuple[Reason, ...]

    def __repr__(self):
        return "Classification(%s, %s)" % (self.state.value, [r.value for r in self.reasons])


def make_classification(state, reasons, field="classification"):
    if type(state) is not ArtifactClassification:
        raise ConstructionError(Reason.ARTIFACT_INTERNAL_MISMATCH, field + ".state",
                                "an artifact classification")
    if type(reasons) is not tuple or any(type(r) is not Reason for r in reasons):
        raise ConstructionError(Reason.ARTIFACT_INTERNAL_MISMATCH, field + ".reasons",
                                "a tuple of reason codes")
    return Classification._seal(state=state, reasons=reasons)


def _verdict(state, reasons):
    return make_classification(state, tuple(reasons))


def classify_artifact(provenance, world, file_facts):
    """UNVERIFIABLE > REVIEW_REQUIRED > STALE > PROVEN_CURRENT, with stable reason codes."""
    if type(provenance) is not ArtifactProvenance:
        raise DomainError("classify_artifact takes an ArtifactProvenance, got %r"
                          % type(provenance).__name__)
    if type(world) is not WorldSnapshot:
        raise DomainError("classify_artifact takes a WorldSnapshot, got %r" % type(world).__name__)
    if type(file_facts) is not ArtifactFileFacts:
        raise DomainError("classify_artifact takes ArtifactFileFacts, got %r"
                          % type(file_facts).__name__)

    if not file_facts.readable or not file_facts.size_ok:
        return _verdict(ArtifactClassification.UNVERIFIABLE, [Reason.ARTIFACT_UNREADABLE])
    if file_facts.links != 1:
        return _verdict(ArtifactClassification.UNVERIFIABLE, [Reason.ARTIFACT_HARDLINKED])

    manifest = provenance.manifest
    sampled = type(manifest) is SampledManifest

    # --- what the world could not establish, it cannot be used to confirm
    unknown = []
    if sampled:
        unknown += [world.world_id, world.newest_promotable]
    if type(manifest.ledger) is Digest or not sampled:
        unknown.append(world.ledger)
    if sampled and type(manifest.live_sweep) is LiveSweepBinding:
        unknown.append(world.live_sweep)
    unknown.append(world.acquisition_integrity)
    if any(v is Absence.UNVERIFIED for v in unknown):
        return _verdict(ArtifactClassification.UNVERIFIABLE, [Reason.WORLD_UNVERIFIED])

    reasons = []

    def add(code):
        if code not in reasons:
            reasons.append(code)

    # --- INTERNAL: is the artifact about the thing the world is about?
    if provenance.scope != world.scope:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    if provenance.workload != world.workload:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    if provenance.finding != world.finding:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    if provenance.candidate != world.candidate:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    if provenance.acquisition not in PROMOTABLE:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    if provenance.sufficiency is not AnalysisSufficiency.SUFFICIENT:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    if manifest.metrics != world.metrics:
        add(Reason.ARTIFACT_INTERNAL_MISMATCH)
    # the identity an artifact may present is decided by the TYPE of manifest it carries: a
    # sampled manifest holds a WorldId, a ledger-only manifest a WorldIdCore. There is no field
    # in which the wrong one could be written.
    if sampled:
        if manifest.world != world.world_id:
            add(Reason.WORLD_ID_MISMATCH)
    else:
        if manifest.world_core != world.world_id_core:
            add(Reason.WORLD_ID_MISMATCH)
    if reasons:
        return _verdict(ArtifactClassification.REVIEW_REQUIRED, reasons)

    # --- INTEGRITY: does the world still hold what the artifact rests on?
    if sampled:
        for ref in manifest.observations:
            seen = world.observation_for(ref.run_id)
            if type(seen) is Absence:
                add(Reason.ARTIFACT_BINDING_MISMATCH)
            elif seen.equivalence != ref.equivalence or seen.order != ref.order:
                # a forged position is a provenance failure, not a freshness question
                add(Reason.ARTIFACT_BINDING_MISMATCH)
            elif seen.conflicted or seen.quarantined:
                add(Reason.ARTIFACT_BINDING_MISMATCH)
    if world.history_integrity is not ContainerIntegrity.INTACT:
        add(Reason.ARTIFACT_CONTAINER_DEGRADED)

    bound_ledger = manifest.ledger if type(manifest.ledger) is Digest else Absence.KNOWN_ABSENT
    if type(bound_ledger) is Digest:
        # absence is not agreement: evidence that is gone cannot satisfy a positive requirement
        if type(world.ledger) is Absence:
            add(Reason.ARTIFACT_BINDING_MISMATCH)
        else:
            if sampled and world.ledger.binding != bound_ledger:
                add(Reason.ARTIFACT_BINDING_MISMATCH)
            if world.ledger.integrity is not ContainerIntegrity.INTACT:
                add(Reason.ARTIFACT_CONTAINER_DEGRADED)
    if sampled and type(manifest.live_sweep) is LiveSweepBinding:
        if type(world.live_sweep) is Absence or world.live_sweep != manifest.live_sweep:
            add(Reason.ARTIFACT_BINDING_MISMATCH)
    if type(world.acquisition_integrity) is AcquisitionIntegrity \
            and provenance.acquisition is not world.acquisition_integrity:
        add(Reason.ARTIFACT_BINDING_MISMATCH)      # an artifact never outranks its acquisition
    if sampled and world.newest_promotable is Absence.KNOWN_ABSENT:
        # the world looked and found nothing promotable, so nothing supports this artifact now
        add(Reason.ARTIFACT_EVIDENCE_NOT_PROMOTABLE)
    elif sampled and manifest.created_at > world.newest_promotable:
        # the other direction of the same question, which the old None could not express: the
        # artifact rests on an observation NEWER than any the world calls promotable, so the
        # evidence under it is not promotable evidence. That is a provenance failure, not
        # staleness -- staleness is the world moving FORWARD past the artifact.
        add(Reason.ARTIFACT_EVIDENCE_NOT_PROMOTABLE)
    if reasons:
        return _verdict(ArtifactClassification.REVIEW_REQUIRED, reasons)

    # --- FRESHNESS, which is never a provenance failure
    if sampled:
        if manifest.created_at < world.newest_promotable:
            return _verdict(ArtifactClassification.STALE, [Reason.ARTIFACT_STALE])
    else:
        if world.ledger.binding != manifest.ledger:
            return _verdict(ArtifactClassification.STALE, [Reason.ARTIFACT_STALE])
    return _verdict(ArtifactClassification.PROVEN_CURRENT, [])
