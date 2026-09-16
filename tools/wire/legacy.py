"""Reading the previous wire generation.

A legacy value never becomes a current value by defaulting, and conversion is not a second
constructor: a schema-3 line is read only far enough to be counted and attributed, through the
LegacyRecord constructor, and every fact the old schema did not carry stays ABSENT.
"""
from evidence.absence import Absence
from evidence.domains import Reason, RecordKind
from evidence.records import make_container, make_legacy_record, make_rejection
from evidence.values import make_run_id, make_scope_id
from . import parse as P
from .errors import WireError
from .record import decode_record

LEGACY_RECORD_SCHEMAS = (3,)


def _soft(make, raw, path, *args):
    """Read a legacy field if it is readable; never invent one if it is not."""
    try:
        return P.built(path, make, raw, *args)
    except WireError:
        return Absence.UNVERIFIED


def decode_legacy_record(raw, path="legacy"):
    if type(raw) is not dict or type(raw.get("envelope")) is not dict:
        raise WireError(Reason.RECORD_SHAPE_INVALID, path, "not a legacy record")
    env = raw["envelope"]
    version = env.get("schema_version")
    if type(version) is not int or version not in LEGACY_RECORD_SCHEMAS:
        raise WireError(Reason.RECORD_UNSUPPORTED_SCHEMA, path, "not a legacy schema")
    kind = Absence.UNVERIFIED
    for member in RecordKind:
        if member.value == env.get("record_type"):
            kind = member
    run_seq = env.get("run_seq")
    if type(run_seq) is not int or type(run_seq) is bool or run_seq < 0:
        run_seq = Absence.UNVERIFIED
    return P.built(path, make_legacy_record, version, kind,
                   _soft(make_scope_id, env.get("scope_id"), path),
                   run_seq,
                   _soft(make_run_id, env.get("run_id"), path))


def decode_mixed_container(lines):
    """Decode a file that may hold both generations. Current, legacy and rejected stay apart."""
    if type(lines) is not list:
        raise WireError(Reason.RECORD_SHAPE_INVALID, "container", "a container is a list")
    records, legacy, rejections = [], [], []
    for index, raw in enumerate(lines):
        try:
            records.append(decode_record(raw, "line[%d]" % index))
            continue
        except WireError as exc:
            current_reason = exc.reason
        try:
            legacy.append(decode_legacy_record(raw, "line[%d]" % index))
        except WireError:
            rejections.append(P.built("container", make_rejection, index, (current_reason,)))
    return P.built("container", make_container, tuple(records), tuple(rejections), tuple(legacy))
