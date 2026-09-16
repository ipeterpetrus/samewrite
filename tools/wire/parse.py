"""The wire PARSER: JSON shape only.

The division of labour in phase 1S is exact, and it is what removes the second validation
authority:

    the parser owns the WIRE SHAPE  -- is this an object, an array, which members exist
    the constructor owns the VALUES -- every domain, every relation, every identity

Nothing here looks at what a value MEANS. There is no digest check, no label check, no enum
check and no cross-field rule in this module: a parser that did any of those would be the second
authority again, one release away from disagreeing with the first.
"""
from evidence.closed import ConstructionError
from evidence.domains import Reason

from .errors import WireError


def members(raw, path, names, reason=Reason.RECORD_SHAPE_INVALID):
    """An object with EXACTLY these members. Membership is wire shape, not semantics."""
    if type(raw) is not dict:
        raise WireError(reason, path, "expected an object, got %s" % type(raw).__name__)
    if any(type(k) is not str for k in raw):
        raise WireError(reason, path, "object keys are strings")
    missing = [n for n in names if n not in raw]
    unknown = [k for k in raw if k not in names]
    if missing:
        raise WireError(reason, path, "missing %s" % sorted(missing))
    if unknown:
        raise WireError(reason, path, "unknown member %s" % sorted(unknown))
    return raw


def mapping(raw, path, reason=Reason.RECORD_SHAPE_INVALID):
    """An open object used as a map. Its KEYS are values, so the constructor validates them."""
    if type(raw) is not dict:
        raise WireError(reason, path, "expected an object, got %s" % type(raw).__name__)
    if any(type(k) is not str for k in raw):
        raise WireError(reason, path, "object keys are strings")
    # member ORDER is not evidence: a JSON object has no semantic member order, and the
    # canonical encoder sorts keys. The constructor canonicalises and refuses duplicates.
    return tuple((k, raw[k]) for k in raw)


def array(raw, path, reason=Reason.RECORD_SHAPE_INVALID):
    if type(raw) is not list:
        raise WireError(reason, path, "expected an array, got %s" % type(raw).__name__)
    return raw


def tagged(raw, path, reason=Reason.CERT_BAD_TYPE):
    """The three-state wire form. Returns ("absent"|"unverified"|"present", value)."""
    if type(raw) is not dict or "state" not in raw:
        raise WireError(reason, path, "expected {state: present|absent|unverified}")
    state = raw["state"]
    if state == "present":
        members(raw, path, ("state", "value"), reason)
        return "present", raw["value"]
    members(raw, path, ("state",), reason)
    if state in ("absent", "unverified"):
        return state, None
    raise WireError(reason, path, "state is present, absent or unverified, got %r" % (state,))


def built(path, make, *args, **kwargs):
    """Call the ONE constructor for a type and report its refusal in wire terms.

    The reason code and the field come from the constructor. The parser adds only WHERE in the
    document it was reading, which is the one thing the constructor cannot know.
    """
    try:
        return make(*args, **kwargs)
    except ConstructionError as exc:
        raise WireError(exc.reason if type(exc.reason) is Reason else Reason.RECORD_SHAPE_INVALID,
                        "%s.%s" % (path, exc.field), exc.detail) from None


def schema_version(raw, path, expected, reason):
    """Identifying the wire generation is a PARSER job: it decides which reader applies."""
    if type(raw) is not int or raw != expected:
        raise WireError(reason, path, "this reader reads schema %r, got %r" % (expected, raw))
    return raw
