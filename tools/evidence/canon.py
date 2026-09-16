"""Appendix A.1 canonical form, over TYPED structures.

The old encoder walked raw dicts and lists, which is exactly the representation this phase
removes from the kernel. Here the canonical form is its own tiny structure -- an ordered pair
list and a sequence -- so a validated object renders itself without any dict ever existing
inside the kernel, and the byte-level guarantee is unchanged: same semantic value, same bytes.
"""
import hashlib


class CanonError(ValueError):
    """A value with no canonical form under A.1."""


MAX_DEPTH = 64


class CanonMap(object):
    """An object in canonical form: ordered (key, value) pairs, keys unique."""

    __slots__ = ("pairs",)

    def __init__(self, pairs):
        self.pairs = tuple(pairs)

    def __repr__(self):
        return "CanonMap(%r)" % (self.pairs,)


class CanonSeq(object):
    """An array in canonical form; order is the caller's and is preserved exactly."""

    __slots__ = ("items",)

    def __init__(self, items):
        self.items = tuple(items)

    def __repr__(self):
        return "CanonSeq(%r)" % (self.items,)


def _encode_str(s):
    try:
        s.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanonError("lone surrogates are an error: %s" % exc) from None
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif o == 0x08:
            out.append("\\b")
        elif o == 0x0C:
            out.append("\\f")
        elif o == 0x0A:
            out.append("\\n")
        elif o == 0x0D:
            out.append("\\r")
        elif o == 0x09:
            out.append("\\t")
        elif o < 0x20:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _emit(value, depth, parts):
    if depth > MAX_DEPTH:
        raise CanonError("structure deeper than MAX_DEPTH=%d" % MAX_DEPTH)
    if value is None:
        parts.append("null")
        return
    if value is True:
        parts.append("true")
        return
    if value is False:
        parts.append("false")
        return
    if isinstance(value, float):
        raise CanonError("floats are not permitted in a digested structure")
    if isinstance(value, int):
        if type(value) is not int:
            raise CanonError("integer subclasses are not permitted")
        parts.append(str(value))
        return
    if isinstance(value, str):
        if type(value) is not str:
            raise CanonError("string subclasses are not permitted")
        parts.append(_encode_str(value))
        return
    if isinstance(value, CanonSeq):
        parts.append("[")
        for i, item in enumerate(value.items):
            if i:
                parts.append(",")
            _emit(item, depth + 1, parts)
        parts.append("]")
        return
    if isinstance(value, CanonMap):
        keyed = []
        for k, v in value.pairs:
            if type(k) is not str:
                raise CanonError("object keys must be strings, got %r" % type(k).__name__)
            try:
                keyed.append((k.encode("utf-8"), k, v))
            except UnicodeEncodeError:
                raise CanonError("lone surrogate in an object key") from None
        keyed = sorted(keyed, key=lambda t: t[0])
        seen = set()
        parts.append("{")
        for i, (raw, k, v) in enumerate(keyed):
            if raw in seen:
                raise CanonError("duplicate key %r" % k)
            seen.add(raw)
            if i:
                parts.append(",")
            parts.append(_encode_str(k))
            parts.append(":")
            _emit(v, depth + 1, parts)
        parts.append("}")
        return
    raise CanonError("type %r has no canonical form" % type(value).__name__)


def encode(value):
    """The canonical UTF-8 bytes of a canonical-form value."""
    parts = []
    _emit(value, 0, parts)
    return "".join(parts).encode("utf-8")


def sha256_hex(value):
    """64 lowercase hex characters over the canonical bytes."""
    return hashlib.sha256(encode(value)).hexdigest()
