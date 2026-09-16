"""Validated object back to raw wire values. This writer emits the CURRENT generation only.

Encoding lives in the wire package for the same reason decoding does: it is the only place a raw
container is allowed to exist. Every decoder has an encoder here, and the round-trip property
`decode(encode(x)) == x` is what keeps the two halves of the boundary honest.
"""
from evidence.absence import Absence
from evidence.containers import HEAD_SCHEMA_VERSION, LEDGER_SCHEMA_VERSION
from evidence.provenance import (ARTIFACT_SCHEMA_VERSION, MANIFEST_SCHEMA_VERSION,
                                 SampledManifest)
from evidence.records import (CERT_SCHEMA_VERSION, COUNTERS, EVENT_TYPES,
                              RECORD_SCHEMA_VERSION, QuarantineBody, QuarantineLostBody,
                              RestoreBody, RotationBody, SWEEP_TYPES)
from evidence.world import WORLD_SCHEMA_VERSION


def _counts(named):
    return {c.name: c.value for c in named.items}


def _tag(value, encode_value):
    if value is Absence.KNOWN_ABSENT:
        return {"state": "absent"}
    if value is Absence.UNVERIFIED:
        return {"state": "unverified"}
    return {"state": "present", "value": encode_value(value)}


def envelope(env, kind):
    return {"schema_version": RECORD_SCHEMA_VERSION, "record_type": kind.value,
            "run_id": env.run_id.text, "scope_id": env.scope.text, "run_seq": env.run_seq,
            "prev_digest": None if type(env.prev) is Absence else env.prev.hex}


def certificate(cert):
    out = {"workload_class": cert.workload.text, "sample_policy": cert.sample_policy.value,
           "sample_bound": None if type(cert.sample_bound) is Absence else cert.sample_bound,
           "frozen_selection": [{"path_digest": s.path.hex, "dev": s.dev, "inode": s.inode,
                                 "size": s.size, "mtime_ns": s.mtime_ns}
                                for s in cert.frozen_selection],
           "discovery_config_digest": cert.discovery_config_digest.hex,
           "parser_contract_version": cert.parser_contract_version,
           "host_profile_id": cert.host_profile_id.hex, "writer_version": cert.writer_version,
           "completed_at": cert.completed_at.seconds,
           "asserted_integrity": (None if type(cert.asserted_integrity) is Absence
                                  else cert.asserted_integrity.value)}
    for name in COUNTERS:
        out[name] = getattr(cert, name)
    return out


def payload(pay):
    return {"shares": _counts(pay.shares), "bpt": pay.bpt, "ts": pay.ts.seconds,
            "sessions": pay.sessions, "turns": pay.turns, "carry_bytes": pay.carry_bytes,
            "sample_manifest": [{"path_digest": e.path.hex, "content_digest": e.content.hex}
                                for e in pay.sample_manifest]}


def _scope_digests(value):
    return {e.scope.text: e.digest.hex for e in value.items}


def _scope_seqs(value):
    return {e.scope.text: e.run_seq for e in value.items}


def body(value):
    if type(value) is QuarantineBody:
        return {"quarantine_file_digest": value.quarantine_file_digest.hex,
                "line_digests": [d.hex for d in value.line_digests], "reason": value.reason}
    if type(value) is QuarantineLostBody:
        return {"expected_file_digest": value.expected_file_digest.hex,
                "observed_state": value.observed_state.value, "count": value.count,
                "reason": value.reason}
    if type(value) is RotationBody:
        return {"archive_digest": value.archive_digest.hex,
                "archive_last_digests": _scope_digests(value.archive_last_digests),
                "first_run_seqs": _scope_seqs(value.first_run_seqs),
                "last_run_seqs": _scope_seqs(value.last_run_seqs), "count": value.count}
    if type(value) is RestoreBody:
        return {"restored_digest": value.restored_digest.hex,
                "highest_run_seq": value.highest_run_seq,
                "pre_restore_integrity": value.pre_restore_integrity.value,
                "pre_restore_reason": value.pre_restore_reason}
    raise TypeError("no encoder for %r" % type(value).__name__)


def record(value):
    if type(value) in SWEEP_TYPES:
        return {"envelope": envelope(value.envelope, value.kind),
                "payload": payload(value.payload),
                "certificate": certificate(value.certificate)}
    if type(value) in EVENT_TYPES:
        return {"envelope": envelope(value.envelope, value.kind), "body": body(value.body)}
    raise TypeError("no encoder for %r" % type(value).__name__)


def head(value):
    return {"schema_version": HEAD_SCHEMA_VERSION,
            "scopes": [{"scope_id": e.scope.text, "highest_run_seq": e.highest_run_seq,
                        "head_digest": e.head_digest.hex,
                        "observation_count": e.observation_count,
                        "updated_at": e.updated_at.seconds} for e in value.entries]}


def ledger_certificate(c):
    return {"cert_schema": LEDGER_SCHEMA_VERSION, "scope_id": c.scope.text,
            "workload_class": c.workload.text, "host_profile_id": c.host_profile_id.hex,
            "discovery_config_digest": c.discovery_config_digest.hex,
            "ledger_binding": c.ledger_binding.hex,
            "parser_contract_version": c.parser_contract_version,
            "lines_total": c.lines_total, "lines_rejected": c.lines_rejected,
            "events_known": c.events_known, "events_unknown": c.events_unknown,
            "writes_observed": c.writes_observed, "checked": c.checked, "denied": c.denied,
            "first_ts": None if type(c.first_ts) is Absence else c.first_ts.seconds,
            "last_ts": None if type(c.last_ts) is Absence else c.last_ts.seconds}


def live_sweep(value):
    return {"sample_id": value.sample.hex, "sample_manifest_digest": value.sample_manifest.hex,
            "certificate_digest": value.certificate.hex}


def world(w):
    return {"world_schema": WORLD_SCHEMA_VERSION, "scope_id": w.scope.text,
            "workload_class": w.workload.text, "finding_id": w.finding.text,
            "candidate_id": w.candidate.text, "world_id_core": w.world_id_core.hex,
            "world_id": _tag(w.world_id, lambda v: v.hex),
            "history_integrity": w.history_integrity.value,
            "acquisition_integrity": _tag(w.acquisition_integrity, lambda v: v.value),
            "ledger": _tag(w.ledger, lambda v: {"ledger_binding": v.binding.hex,
                                                "integrity": v.integrity.value}),
            "live_sweep": _tag(w.live_sweep, live_sweep),
            "newest_promotable": _tag(w.newest_promotable,
                                      lambda v: [v.run_seq, v.run_id.text]),
            "observations": [{"order_key": [o.order.run_seq, o.order.run_id.text],
                              "equivalence_digest": o.equivalence.hex,
                              "conflicted": o.conflicted, "quarantined": o.quarantined}
                             for o in w.observations],
            "metrics": _counts(w.metrics)}


def manifest(m):
    if type(m) is SampledManifest:
        return {"manifest_schema": MANIFEST_SCHEMA_VERSION, "kind": "sampled",
                "world_id": m.world.hex,
                "observations": [{"order_key": [o.order.run_seq, o.order.run_id.text],
                                  "equivalence_digest": o.equivalence.hex}
                                 for o in m.observations],
                "ledger_binding": None if type(m.ledger) is Absence else m.ledger.hex,
                "live_sweep": (None if type(m.live_sweep) is Absence
                               else live_sweep(m.live_sweep)),
                "metrics": _counts(m.metrics)}
    return {"manifest_schema": MANIFEST_SCHEMA_VERSION, "kind": "ledger_only",
            "world_id_core": m.world_core.hex, "ledger_binding": m.ledger.hex,
            "metrics": _counts(m.metrics)}


def provenance(p):
    return {"artifact_schema": ARTIFACT_SCHEMA_VERSION, "candidate_id": p.candidate.text,
            "finding_id": p.finding.text, "scope_id": p.scope.text,
            "workload_class": p.workload.text, "acquisition_integrity": p.acquisition.value,
            "analysis_sufficiency": p.sufficiency.value,
            "created_by_version": p.created_by_version, "evidence_manifest": manifest(p.manifest)}


def transaction_facts(f):
    out = {"op": _tag(f.op, lambda v: v.value), "txn_open": f.txn_open}
    for name in ("journalled_record_present", "records_still_in_active", "tmp_present",
                 "archive_present", "head_matches_active"):
        out[name] = _tag(getattr(f, name), lambda v: v)
    return out
