"""Section 4 + A.5 - identities over typed values. Nothing here sorts anything."""
from . import forms as f
from .absence import Absence
from .canon import CanonMap, CanonSeq
from .closed import ConstructionError
from .domains import DomainError, Reason, SamplePolicy, require, require_all, require_int
from .records import (AcquisitionCertificate, EVENT_TYPES, ManifestEntry, SWEEP_TYPES)
from .values import (Digest, ScopeId, SourceId, WorkloadId, WorldId, WorldIdCore, digest_of,
                     make_sample_id, make_world_id, make_world_id_core, seq_canon)

RECORD_TYPES = SWEEP_TYPES + EVENT_TYPES


def world_id_core(scope, workload, discovery_config_digest, parser_contract_version):
    """Is this the same SUBJECT? Every source can compute it; the host is deliberately absent."""
    require(scope, ScopeId, "scope")
    require(workload, WorkloadId, "workload")
    require(discovery_config_digest, Digest, "discovery_config_digest")
    require_int(parser_contract_version, "parser_contract_version", 0)
    form = CanonMap([("scope_id", scope.text), ("workload_class", workload.text),
                     ("discovery_config_digest", discovery_config_digest.hex),
                     ("parser_contract_version", parser_contract_version)])
    return make_world_id_core(digest_of(form).hex, "world_id_core")


def world_id(core, sample_policy, sample_bound):
    """... sampled the same way? The sampling dimension is part of the identity."""
    require(core, WorldIdCore, "world_id_core")
    require(sample_policy, SamplePolicy, "sample_policy")
    if type(sample_bound) is not Absence:
        require_int(sample_bound, "sample_bound", 1)
    bound = sample_bound if type(sample_bound) is int else None
    form = CanonMap([("world_id_core", core.hex), ("sample_policy", sample_policy.value),
                     ("sample_bound", bound)])
    return make_world_id(digest_of(form).hex, "world_id")


def sample_id(world, selection):
    """Is this the same file set? The selection is already in canonical order."""
    require(world, WorldId, "world_id")
    require_all(selection, SourceId, "frozen_selection")
    form = CanonMap([("world_id", world.hex), ("sources", seq_canon(selection))])
    return make_sample_id(digest_of(form).hex, "sample_id")


def sample_manifest_digest(entries):
    """Did we read the same bytes? Again: the carried order is the canonical one."""
    require_all(entries, ManifestEntry, "sample_manifest")
    return digest_of(CanonSeq([e.canon() for e in entries]))


def certificate_world_id(certificate, scope):
    require(certificate, AcquisitionCertificate, "certificate")
    core = world_id_core(scope, certificate.workload, certificate.discovery_config_digest,
                         certificate.parser_contract_version)
    return world_id(core, certificate.sample_policy, certificate.sample_bound)


def certificate_sample_id(certificate, scope):
    require(certificate, AcquisitionCertificate, "certificate")
    return sample_id(certificate_world_id(certificate, scope), certificate.frozen_selection)


def population_id(scope, workload, members):
    """WHICH observations an analysis rests on, as one stable identity.

    Over what the members SAY (their equivalence digests) and where they sit (their positions),
    so the identity is reproducible from the evidence itself and independent of read order.
    """
    require(scope, ScopeId, "scope")
    require(workload, WorkloadId, "workload")
    if type(members) is not tuple:
        raise DomainError("a population identity is computed over a tuple of records")
    for record in members:
        _require_record(record)
    form = CanonMap([("scope_id", scope.text), ("workload_class", workload.text),
                     ("observations", CanonSeq(
                         [CanonMap([("order_key", m.envelope.order.canon()),
                                    ("equivalence_digest", m.equivalence().hex)])
                          for m in members]))])
    return digest_of(form)


def observation_identity(record):
    """Section 7: WHO observed WHAT."""
    _require_record(record)
    return (record.envelope.run_id, record.envelope.scope)


def record_digest(record):
    """The digest a successor links to."""
    _require_record(record)
    return digest_of(record)


def _require_record(record):
    if type(record) not in RECORD_TYPES:
        raise DomainError("a validated record is required, got %r" % type(record).__name__)


def canonical_newest(records):
    """The newest record of a set, by a TOTAL order: position, then the record digest.

    Two records can share a position -- the same run at the same sequence, written twice -- and a
    comparison that only asks `<` leaves the winner to whoever was read first. Every consumer
    that needs a newest record asks here, so there is one rule and one place to change it.
    """
    if type(records) is not tuple or not records:
        raise DomainError("a newest record is chosen from a non-empty tuple")
    best = None
    for record in records:
        _require_record(record)
        key = (record.envelope.order._sort(), record_digest(record).hex)
        if best is None or key > best[0]:
            best = (key, record)
    return best[1]


def canonical_order(records):
    """The same total order, as a sort key: a multiset has one arrangement."""
    if type(records) is not tuple:
        raise DomainError("canonical_order takes a tuple of validated records")
    for record in records:
        _require_record(record)
    return tuple(sorted(records,
                        key=lambda r: (r.envelope.order._sort(), record_digest(r).hex)))


def discovery_config_digest(config):
    from .preimages import DiscoveryConfig
    require(config, DiscoveryConfig, "discovery_config")
    return digest_of(config)


def host_profile_id(profile):
    """A host profile identifier is a ShortDigest, built by its own constructor like everything
    else: a 16-character slice of a string is not a validated value."""
    from .preimages import HostProfile
    from .values import make_short_digest
    require(profile, HostProfile, "host_profile")
    return make_short_digest(digest_of(profile).hex[:16], "host_profile_id")
