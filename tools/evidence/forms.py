"""The pure shape predicates, in one place, so the decoder and the type invariant agree.

A validated type's invariant and the decoder that establishes it must be the same rule. Keeping
them in two places is how they drift, so both call these.
"""
import re
import unicodedata

from .label import LabelRejected, validate_label

_UUID4 = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_HEX = {12: re.compile(r"\A[0-9a-f]{12}\Z"), 16: re.compile(r"\A[0-9a-f]{16}\Z"),
        64: re.compile(r"\A[0-9a-f]{64}\Z")}
_IDENTIFIER = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")


def is_bool(v):
    """Python says isinstance(True, int); the wire contract does not, and neither does this."""
    return v is True or v is False


def is_int(v):
    return type(v) is int


def is_nat(v):
    return type(v) is int and v >= 0


def is_pos(v):
    return type(v) is int and v >= 1


def is_str(v):
    if type(v) is not str:
        return False
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def hex_of(width):
    """A predicate for a fixed-width lowercase hex string. Total in its own argument too."""
    pattern = _HEX.get(width) if type(width) is int else None

    def check(v):
        return pattern is not None and is_str(v) and bool(pattern.match(v))
    check.__name__ = "hex%s" % (width if type(width) is int else "?")
    return check


hex12 = hex_of(12)
hex16 = hex_of(16)
hex64 = hex_of(64)


def is_uuid4(v):
    return is_str(v) and bool(_UUID4.match(v))


def is_identifier(v):
    return is_str(v) and bool(_IDENTIFIER.match(v))


def is_carried_label(v):
    """A label that CARRIES its NFC form, not one that merely normalises to it."""
    if not is_str(v):
        return False
    try:
        return validate_label(v) == v
    except LabelRejected:
        return False


def _names(kinds):
    return "_".join(getattr(k, "__name__", str(k)) for k in kinds)


def inst(*kinds):
    """A predicate for `isinstance`. Total: a caller passing a non-type gets False, not a crash."""
    def check(v):
        try:
            return isinstance(v, kinds)
        except TypeError:
            return False
    check.__name__ = "instance_of_" + _names(kinds)
    return check


def tuple_of(*kinds):
    def check(v):
        if type(v) is not tuple:
            return False
        try:
            return all(isinstance(i, kinds) for i in v)
        except TypeError:
            return False
    check.__name__ = "tuple_of_" + _names(kinds)
    return check


def either(*checks):
    def check(v):
        return any(c(v) for c in checks)
    check.__name__ = "either"
    return check


def ascending_unique(key):
    def check(values):
        if type(values) is not tuple:
            return False
        keys = [key(v) for v in values]
        return keys == sorted(keys) and len(set(keys)) == len(keys)
    check.__name__ = "ascending_unique"
    return check
