"""JSON text to raw values, under A.1's restrictions, and raw values to canonical form.

Parsing is a wire concern, so the raw value never leaves this package except through a decoder.
`to_canon` exists for one reason: the normative canonical-JSON vectors are expressed as JSON, and
the kernel's encoder only speaks canonical form.
"""
import json

from evidence.canon import CanonError, CanonMap, CanonSeq, MAX_DEPTH

_LEADING_ZERO_CHARS = "0123456789"


def _reject_number_forms(text):
    """Scan number tokens outside strings for minus zero, leading zeros and a leading plus."""
    i, n, in_str = 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "+":
            raise CanonError("no leading plus in a number")
        if c == "-" or c.isdigit():
            j = i
            while j < n and (text[j].isdigit() or text[j] in "-+.eE"):
                j += 1
            tok = text[i:j]
            if tok.startswith("-0") and not (len(tok) > 2 and tok[2] in ".eE"):
                raise CanonError("minus zero is an error: %r" % tok)
            body = tok[1:] if tok.startswith("-") else tok
            if len(body) > 1 and body[0] == "0" and body[1] in _LEADING_ZERO_CHARS:
                raise CanonError("no leading zeros in a number: %r" % tok)
            i = j
            continue
        i += 1


def _no_float(_s):
    raise CanonError("floats are not permitted in a digested structure")


def _no_constant(name):
    raise CanonError("%s has no representation" % name)


def _pairs_hook(items):
    out = {}
    for k, v in items:
        if k in out:
            raise CanonError("duplicate keys are an error: %r" % k)
        out[k] = v
    return out


def _reject_surrogates(value, depth):
    if depth > MAX_DEPTH:
        raise CanonError("structure deeper than MAX_DEPTH=%d" % MAX_DEPTH)
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise CanonError("lone surrogates are an error") from None
    elif type(value) is list:
        for item in value:
            _reject_surrogates(item, depth + 1)
    elif type(value) is dict:
        for k, v in value.items():
            _reject_surrogates(k, depth + 1)
            _reject_surrogates(v, depth + 1)


def strict_loads(data):
    """Parse JSON under A.1's restrictions: no duplicate keys, floats, NaN, Infinity, minus zero."""
    if not isinstance(data, (bytes, bytearray)):
        raise CanonError("strict_loads takes bytes, got %r" % type(data).__name__)
    if data.startswith(b"\xef\xbb\xbf"):
        raise CanonError("byte-order mark is not permitted")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CanonError("input is not valid UTF-8: %s" % exc) from None
    _reject_number_forms(text)
    try:
        value = json.loads(text, parse_float=_no_float, parse_constant=_no_constant,
                           object_pairs_hook=_pairs_hook)
    except CanonError:
        raise
    except ValueError as exc:
        raise CanonError("not parseable: %s" % exc) from None
    _reject_surrogates(value, 0)
    return value


def to_canon(value, depth=0):
    """A raw JSON value in canonical form, so the kernel encoder can render it."""
    if depth > MAX_DEPTH:
        raise CanonError("structure deeper than MAX_DEPTH=%d" % MAX_DEPTH)
    if type(value) is dict:
        return CanonMap([(k, to_canon(v, depth + 1)) for k, v in value.items()])
    if type(value) is list:
        return CanonSeq([to_canon(v, depth + 1) for v in value])
    return value
