"""The history record decoder: read the shape, then call the record's one constructor."""
from evidence.absence import Absence
from evidence.domains import (AcquisitionIntegrity, ContainerIntegrity, ObservedState, Reason,
                              RecordKind, SamplePolicy)
from evidence.records import (COUNTERS, EVENT_FOR_KIND, RECORD_SCHEMA_VERSION, SWEEP_FOR_KIND,
                              make_carry_sweep, make_carry_sweep_failed, make_certificate,
                              make_container, make_envelope, make_payload,
                              make_quarantine_body, make_quarantine_event,
                              make_quarantine_lost_body, make_quarantine_lost_event,
                              make_rejection, make_restore_body, make_restore_event,
                              make_rotation_body, make_rotation_event)
from evidence.values import (make_digest, make_epoch, make_manifest_entry, make_named_counts,
                             make_path_digest, make_run_id, make_scope_digests, make_scope_id,
                             make_scope_seqs, make_short_digest, make_source_id,
                             make_workload_id)
from . import parse as P
from .errors import WireError

ENVELOPE_FIELDS = ("schema_version", "record_type", "run_id", "scope_id", "run_seq",
                   "prev_digest")
SWEEP_MEMBERS = ("envelope", "payload", "certificate")
EVENT_MEMBERS = ("envelope", "body")
PAYLOAD_FIELDS = ("shares", "bpt", "ts", "sessions", "turns", "carry_bytes", "sample_manifest")
CERT_FIELDS = ("workload_class", "sample_policy", "sample_bound", "frozen_selection",
               "discovery_config_digest", "parser_contract_version", "host_profile_id",
               "writer_version", "completed_at", "asserted_integrity") + COUNTERS
SOURCE_FIELDS = ("path_digest", "dev", "inode", "size", "mtime_ns")
MANIFEST_ENTRY_FIELDS = ("path_digest", "content_digest")
BODY_FIELDS = {
    RecordKind.HISTORY_QUARANTINE: ("quarantine_file_digest", "line_digests", "reason"),
    RecordKind.HISTORY_QUARANTINE_LOST: ("expected_file_digest", "observed_state", "count",
                                         "reason"),
    RecordKind.HISTORY_ROTATED: ("archive_digest", "archive_last_digests", "first_run_seqs",
                                 "last_run_seqs", "count"),
    RecordKind.HISTORY_RESTORED: ("restored_digest", "highest_run_seq", "pre_restore_integrity",
                                  "pre_restore_reason"),
}


def _fail_empty(path):
    """Only a mutant calls this: the parser does not decide the workload domain."""
    raise WireError(Reason.CERT_BAD_TYPE, path, "empty workload refused by the parser")


def _enum(kind, raw, path, reason=Reason.CERT_BAD_TYPE):
    """Selecting a variant from a tag is a PARSER job: it decides which constructor applies."""
    for member in kind:
        if member.value == raw:
            return member
    raise WireError(reason, path, "%r is not one of %s" % (raw, [m.value for m in kind]))


def _kind_of(raw, path):
    body = P.members(raw, path, ENVELOPE_FIELDS, Reason.ENVELOPE_MISSING_KEY)
    P.schema_version(body["schema_version"], path + ".schema_version", RECORD_SCHEMA_VERSION,
                     Reason.RECORD_UNSUPPORTED_SCHEMA)
    return body, _enum(RecordKind, body["record_type"], path + ".record_type",
                       Reason.RECORD_UNKNOWN_TYPE)


def _envelope(body, path):
    prev_raw = body["prev_digest"]
    prev = (Absence.KNOWN_ABSENT if prev_raw is None
            else P.built(path, make_digest, prev_raw, "prev_digest",
                         Reason.ENVELOPE_BAD_TYPE))
    return P.built(path, make_envelope,
                   P.built(path, make_run_id, body["run_id"]),
                   P.built(path, make_scope_id, body["scope_id"]),
                   body["run_seq"], prev)


def _source(raw, path):
    body = P.members(raw, path, SOURCE_FIELDS, Reason.FROZEN_SELECTION_INVALID)
    return P.built(path, make_source_id,
                   P.built(path, make_path_digest, body["path_digest"], "path_digest",
                           Reason.FROZEN_SELECTION_INVALID),
                   body["dev"], body["inode"], body["size"], body["mtime_ns"])


def _manifest_entry(raw, path):
    body = P.members(raw, path, MANIFEST_ENTRY_FIELDS, Reason.PAYLOAD_BAD_TYPE)
    return P.built(path, make_manifest_entry,
                   P.built(path, make_path_digest, body["path_digest"], "path_digest",
                           Reason.PAYLOAD_BAD_TYPE),
                   P.built(path, make_digest, body["content_digest"], "content_digest",
                           Reason.PAYLOAD_BAD_TYPE))


def _payload(raw, path):
    body = P.members(raw, path, PAYLOAD_FIELDS, Reason.PAYLOAD_MISSING_KEY)
    entries = tuple(_manifest_entry(e, "%s.sample_manifest[%d]" % (path, i))
                    for i, e in enumerate(P.array(body["sample_manifest"],
                                                  path + ".sample_manifest",
                                                  Reason.PAYLOAD_BAD_TYPE)))
    shares = P.built(path, make_named_counts,
                     P.mapping(body["shares"], path + ".shares", Reason.PAYLOAD_BAD_TYPE),
                     "shares", Reason.PAYLOAD_BAD_TYPE)
    return P.built(path, make_payload, shares, body["bpt"],
                   P.built(path, make_epoch, body["ts"], "ts", Reason.PAYLOAD_BAD_TYPE),
                   body["sessions"], body["turns"], body["carry_bytes"], entries)


def _certificate(raw, path):
    body = P.members(raw, path, CERT_FIELDS, Reason.CERT_MISSING_KEY)
    policy = body["sample_policy"]
    bound = (Absence.KNOWN_ABSENT if body["sample_bound"] is None else body["sample_bound"])
    asserted = (Absence.KNOWN_ABSENT if body["asserted_integrity"] is None
                else body["asserted_integrity"])
    selection = tuple(_source(s, "%s.frozen_selection[%d]" % (path, i))
                      for i, s in enumerate(P.array(body["frozen_selection"],
                                                    path + ".frozen_selection",
                                                    Reason.FROZEN_SELECTION_INVALID)))
    return P.built(path, make_certificate,
                   P.built(path, make_workload_id, body["workload_class"]),
                   policy, bound, selection,
                   P.built(path, make_digest, body["discovery_config_digest"],
                           "discovery_config_digest"),
                   body["parser_contract_version"],
                   P.built(path, make_short_digest, body["host_profile_id"]),
                   body["writer_version"],
                   P.built(path, make_epoch, body["completed_at"], "completed_at"),
                   asserted, {name: body[name] for name in COUNTERS})


def _body(kind, raw, path):
    fields = BODY_FIELDS[kind]
    body = P.members(raw, path, fields)
    if kind is RecordKind.HISTORY_QUARANTINE:
        digests = tuple(P.built(path, make_digest, d, "line_digests",
                                Reason.RECORD_SHAPE_INVALID)
                        for d in P.array(body["line_digests"], path + ".line_digests"))
        return P.built(path, make_quarantine_body,
                       P.built(path, make_digest, body["quarantine_file_digest"],
                               "quarantine_file_digest", Reason.RECORD_SHAPE_INVALID),
                       digests, body["reason"])
    if kind is RecordKind.HISTORY_QUARANTINE_LOST:
        return P.built(path, make_quarantine_lost_body,
                       P.built(path, make_digest, body["expected_file_digest"],
                               "expected_file_digest", Reason.RECORD_SHAPE_INVALID),
                       body["observed_state"], body["count"], body["reason"])
    if kind is RecordKind.HISTORY_ROTATED:
        digests = tuple((scope, P.built(path, make_digest, value, "archive_last_digests",
                                        Reason.RECORD_SHAPE_INVALID))
                        for scope, value in P.mapping(body["archive_last_digests"],
                                                      path + ".archive_last_digests"))
        return P.built(path, make_rotation_body,
                       P.built(path, make_digest, body["archive_digest"], "archive_digest",
                               Reason.RECORD_SHAPE_INVALID),
                       P.built(path, make_scope_digests, digests, "archive_last_digests"),
                       P.built(path, make_scope_seqs,
                               P.mapping(body["first_run_seqs"], path + ".first_run_seqs"),
                               "first_run_seqs"),
                       P.built(path, make_scope_seqs,
                               P.mapping(body["last_run_seqs"], path + ".last_run_seqs"),
                               "last_run_seqs"),
                       body["count"])
    return P.built(path, make_restore_body,
                   P.built(path, make_digest, body["restored_digest"], "restored_digest",
                           Reason.RECORD_SHAPE_INVALID),
                   body["highest_run_seq"], body["pre_restore_integrity"],
                   body["pre_restore_reason"])


EVENT_MAKERS = {RecordKind.HISTORY_QUARANTINE: make_quarantine_event,
                RecordKind.HISTORY_QUARANTINE_LOST: make_quarantine_lost_event,
                RecordKind.HISTORY_ROTATED: make_rotation_event,
                RecordKind.HISTORY_RESTORED: make_restore_event}
SWEEP_MAKERS = {RecordKind.CARRY_SWEEP: make_carry_sweep,
                RecordKind.CARRY_SWEEP_FAILED: make_carry_sweep_failed}


def decode_record(raw, path="record"):
    """A validated record, or WireError. The KIND selects the constructor, and the constructor
    owns everything else: there is no second place where a record decides what it is."""
    if type(raw) is not dict:
        raise WireError(Reason.RECORD_SHAPE_INVALID, path,
                        "a record is an object, got %s" % type(raw).__name__)
    if "envelope" not in raw:
        raise WireError(Reason.ENVELOPE_MISSING_KEY, path, "no envelope")
    env_body, kind = _kind_of(raw["envelope"], path + ".envelope")
    envelope = _envelope(env_body, path + ".envelope")
    if kind in SWEEP_MAKERS:
        body = P.members(raw, path, SWEEP_MEMBERS)
        return P.built(path, SWEEP_MAKERS[kind], envelope,
                       _payload(body["payload"], path + ".payload"),
                       _certificate(body["certificate"], path + ".certificate"))
    body = P.members(raw, path, EVENT_MEMBERS)
    return P.built(path, EVENT_MAKERS[kind], envelope,
                   _body(kind, body["body"], path + ".body"))


def decode_container(lines):
    """Decode a whole history file. Nothing that fails to decode disappears."""
    if type(lines) is not list:
        raise WireError(Reason.RECORD_SHAPE_INVALID, "container",
                        "a container is a list of lines, got %s" % type(lines).__name__)
    records, rejections = [], []
    for index, raw in enumerate(lines):
        try:
            records.append(decode_record(raw, "line[%d]" % index))
        except WireError as exc:
            rejections.append(P.built("container", make_rejection, index, (exc.reason,)))
    return P.built("container", make_container, tuple(records), tuple(rejections), ())
