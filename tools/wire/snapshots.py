"""Decoders for the world snapshot, the artifact provenance header and transaction facts."""
from evidence.absence import Absence
from evidence.domains import (AcquisitionIntegrity, AnalysisSufficiency, ContainerIntegrity,
                              MutatingOp, Reason)
from evidence.provenance import (ARTIFACT_SCHEMA_VERSION, MANIFEST_SCHEMA_VERSION,
                                 make_ledger_only_manifest, make_observation_ref,
                                 make_provenance, make_sampled_manifest)
from evidence.txn import make_transaction_facts
from evidence.values import (make_candidate_id, make_digest, make_finding_id, make_named_counts,
                             make_order_key, make_run_id, make_sample_id, make_scope_id,
                             make_workload_id, make_world_id, make_world_id_core)
from evidence.world import (WORLD_SCHEMA_VERSION, make_file_facts, make_ledger_state,
                            make_live_sweep_binding, make_world_observation,
                            make_world_snapshot)
from . import parse as P
from .errors import WireError

WORLD_FIELDS = ("world_schema", "scope_id", "workload_class", "finding_id", "candidate_id",
                "world_id_core", "world_id", "history_integrity", "acquisition_integrity",
                "ledger", "live_sweep", "newest_promotable", "observations", "metrics")
WORLD_OBSERVATION_FIELDS = ("order_key", "equivalence_digest", "conflicted", "quarantined")
LIVE_SWEEP_FIELDS = ("sample_id", "sample_manifest_digest", "certificate_digest")
LEDGER_STATE_FIELDS = ("ledger_binding", "integrity")
ARTIFACT_FIELDS = ("artifact_schema", "candidate_id", "finding_id", "scope_id", "workload_class",
                   "acquisition_integrity", "analysis_sufficiency", "created_by_version",
                   "evidence_manifest")
SAMPLED_MANIFEST_FIELDS = ("manifest_schema", "kind", "world_id", "observations",
                           "ledger_binding", "live_sweep", "metrics")
LEDGER_MANIFEST_FIELDS = ("manifest_schema", "kind", "world_id_core", "ledger_binding", "metrics")
OBSERVATION_REF_FIELDS = ("order_key", "equivalence_digest")
FACT_FIELDS = ("op", "txn_open", "journalled_record_present", "records_still_in_active",
               "tmp_present", "archive_present", "head_matches_active")
OPTIONAL_FACTS = FACT_FIELDS[2:]
ART = Reason.ARTIFACT_INTERNAL_MISMATCH


def _enum(kind, raw, path, reason):
    for member in kind:
        if member.value == raw:
            return member
    raise WireError(reason, path, "%r is not one of %s" % (raw, [m.value for m in kind]))


def _order_key(raw, path, reason):
    items = P.array(raw, path, reason)
    if len(items) != 2:
        raise WireError(reason, path, "an order key is [run_seq, run_id]")
    return P.built(path, make_order_key, items[0],
                   P.built(path, make_run_id, items[1], "run_id", reason), "order_key", reason)


def _live_sweep(raw, path):
    body = P.members(raw, path, LIVE_SWEEP_FIELDS)
    return P.built(path, make_live_sweep_binding,
                   P.built(path, make_sample_id, body["sample_id"]),
                   P.built(path, make_digest, body["sample_manifest_digest"],
                           "sample_manifest_digest"),
                   P.built(path, make_digest, body["certificate_digest"], "certificate_digest"))


def _ledger_state(raw, path):
    body = P.members(raw, path, LEDGER_STATE_FIELDS)
    return P.built(path, make_ledger_state,
                   P.built(path, make_digest, body["ledger_binding"], "ledger_binding"),
                   body["integrity"])


def _maybe(raw, path, decode, reason=Reason.CERT_BAD_TYPE):
    state, value = P.tagged(raw, path, reason)
    if state == "absent":
        return Absence.KNOWN_ABSENT
    if state == "unverified":
        return Absence.UNVERIFIED
    return decode(value, path + ".value")


def decode_world_snapshot(raw, path="world"):
    body = P.members(raw, path, WORLD_FIELDS, Reason.WORLD_UNVERIFIED)
    P.schema_version(body["world_schema"], path + ".world_schema", WORLD_SCHEMA_VERSION,
                     Reason.WORLD_UNVERIFIED)
    observations = []
    for i, entry in enumerate(P.array(body["observations"], path + ".observations",
                                      Reason.WORLD_UNVERIFIED)):
        at = "%s.observations[%d]" % (path, i)
        fields = P.members(entry, at, WORLD_OBSERVATION_FIELDS, Reason.WORLD_UNVERIFIED)
        observations.append(P.built(at, make_world_observation,
                                    _order_key(fields["order_key"], at + ".order_key",
                                               Reason.WORLD_UNVERIFIED),
                                    P.built(at, make_digest, fields["equivalence_digest"],
                                            "equivalence_digest", Reason.WORLD_UNVERIFIED),
                                    fields["conflicted"], fields["quarantined"]))
    return P.built(path, make_world_snapshot,
                   P.built(path, make_scope_id, body["scope_id"]),
                   P.built(path, make_workload_id, body["workload_class"]),
                   P.built(path, make_finding_id, body["finding_id"], "finding_id",
                           Reason.WORLD_UNVERIFIED),
                   P.built(path, make_candidate_id, body["candidate_id"], "candidate_id",
                           Reason.WORLD_UNVERIFIED),
                   P.built(path, make_world_id_core, body["world_id_core"], "world_id_core",
                           Reason.WORLD_UNVERIFIED),
                   _maybe(body["world_id"], path + ".world_id",
                          lambda v, p: P.built(p, make_world_id, v, "world_id",
                                               Reason.WORLD_UNVERIFIED),
                          Reason.WORLD_UNVERIFIED),
                   body["history_integrity"],
                   _maybe(body["acquisition_integrity"], path + ".acquisition_integrity",
                          lambda v, p: v, Reason.WORLD_UNVERIFIED),
                   _maybe(body["ledger"], path + ".ledger", _ledger_state,
                          Reason.WORLD_UNVERIFIED),
                   _maybe(body["live_sweep"], path + ".live_sweep", _live_sweep,
                          Reason.WORLD_UNVERIFIED),
                   _maybe(body["newest_promotable"], path + ".newest_promotable",
                          lambda v, p: _order_key(v, p, Reason.WORLD_UNVERIFIED),
                          Reason.WORLD_UNVERIFIED),
                   tuple(observations),
                   P.built(path, make_named_counts,
                           P.mapping(body["metrics"], path + ".metrics",
                                     Reason.WORLD_UNVERIFIED),
                           "metrics", Reason.WORLD_UNVERIFIED))


def _observation_ref(raw, path):
    body = P.members(raw, path, OBSERVATION_REF_FIELDS, ART)
    return P.built(path, make_observation_ref,
                   _order_key(body["order_key"], path + ".order_key", ART),
                   P.built(path, make_digest, body["equivalence_digest"], "equivalence_digest",
                           ART))


def _manifest(raw, path):
    """The KIND selects the manifest's constructor; the constructor owns everything else."""
    if type(raw) is not dict or "kind" not in raw:
        raise WireError(ART, path, "an evidence manifest names its kind")
    P.schema_version(raw.get("manifest_schema"), path + ".manifest_schema",
                     MANIFEST_SCHEMA_VERSION, ART)
    if raw["kind"] == "sampled":
        body = P.members(raw, path, SAMPLED_MANIFEST_FIELDS, ART)
        refs = tuple(_observation_ref(o, "%s.observations[%d]" % (path, i))
                     for i, o in enumerate(P.array(body["observations"],
                                                   path + ".observations", ART)))
        ledger = (Absence.KNOWN_ABSENT if body["ledger_binding"] is None
                  else P.built(path, make_digest, body["ledger_binding"], "ledger_binding", ART))
        live = (Absence.KNOWN_ABSENT if body["live_sweep"] is None
                else _live_sweep(body["live_sweep"], path + ".live_sweep"))
        return P.built(path, make_sampled_manifest,
                       P.built(path, make_world_id, body["world_id"], "world_id", ART),
                       refs, ledger, live,
                       P.built(path, make_named_counts,
                               P.mapping(body["metrics"], path + ".metrics", ART), "metrics",
                               ART))
    if raw["kind"] == "ledger_only":
        body = P.members(raw, path, LEDGER_MANIFEST_FIELDS, ART)
        return P.built(path, make_ledger_only_manifest,
                       P.built(path, make_world_id_core, body["world_id_core"], "world_id_core",
                               ART),
                       P.built(path, make_digest, body["ledger_binding"], "ledger_binding", ART),
                       P.built(path, make_named_counts,
                               P.mapping(body["metrics"], path + ".metrics", ART), "metrics",
                               ART))
    raise WireError(ART, path + ".kind",
                    "an evidence manifest is sampled or ledger_only, got %r" % (raw["kind"],))


def decode_artifact_provenance(raw, path="artifact"):
    body = P.members(raw, path, ARTIFACT_FIELDS, ART)
    P.schema_version(body["artifact_schema"], path + ".artifact_schema",
                     ARTIFACT_SCHEMA_VERSION, ART)
    return P.built(path, make_provenance,
                   P.built(path, make_candidate_id, body["candidate_id"], "candidate_id", ART),
                   P.built(path, make_finding_id, body["finding_id"], "finding_id", ART),
                   P.built(path, make_scope_id, body["scope_id"]),
                   P.built(path, make_workload_id, body["workload_class"]),
                   body["acquisition_integrity"], body["analysis_sufficiency"],
                   body["created_by_version"],
                   _manifest(body["evidence_manifest"], path + ".evidence_manifest"))


def decode_artifact_file_facts(raw, path="file_facts"):
    body = P.members(raw, path, ("readable", "links", "size_ok"), Reason.ARTIFACT_UNREADABLE)
    return P.built(path, make_file_facts, body["readable"], body["links"], body["size_ok"])


def decode_transaction_facts(raw, path="facts"):
    body = P.members(raw, path, FACT_FIELDS, Reason.RECORD_SHAPE_INVALID)
    op = _maybe(body["op"], path + ".op", lambda v, p: v, Reason.RECORD_SHAPE_INVALID)
    facts = {}
    for name in OPTIONAL_FACTS:
        facts[name] = _maybe(body[name], path + "." + name, lambda v, p: v,
                             Reason.RECORD_SHAPE_INVALID)
    return P.built(path, make_transaction_facts, op, body["txn_open"], facts)
