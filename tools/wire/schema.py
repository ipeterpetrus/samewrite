"""Decoder for the output-schema description compared by section 13."""
from evidence.domains import Reason
from evidence.schema_policy import FieldKind, make_field_spec, make_output_schema
from . import parse as P
from .errors import WireError

FIELD_SPEC_FIELDS = ("kind", "required", "semantics", "domain")


def decode_schema(raw, path="schema"):
    if type(raw) is not dict:
        raise WireError(Reason.RECORD_SHAPE_INVALID, path, "a schema is an object of fields")
    if any(type(k) is not str for k in raw):
        raise WireError(Reason.RECORD_SHAPE_INVALID, path, "field names are strings")
    specs = []
    for name in raw:
        at = "%s.%s" % (path, name)
        body = P.members(raw[name], at, FIELD_SPEC_FIELDS)
        specs.append(P.built(at, make_field_spec, name, body["kind"], body["required"],
                             body["semantics"], tuple(P.array(body["domain"], at + ".domain"))))
    return P.built(path, make_output_schema, tuple(specs))
