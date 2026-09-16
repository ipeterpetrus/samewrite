"""Section 12 - validate the label, then name it. Slugging never sanitises.

Ported unchanged in behaviour from the phase 1 kernel: this rule survived every review round.
It stays in the evidence package because a ScopeId's validity is part of its type.
"""
import hashlib
import re
import unicodedata

RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} \
    | {"LPT%d" % i for i in range(1, 10)}
BIDI = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}
ALLOWED_PUNCT = {".", "_", "-"}
MAX_CODE_POINTS = 64
MAX_BYTES = 192
SLUG_BODY = 32
SLUG_HASH = 16


class LabelRejected(ValueError):
    def __init__(self, reason, label):
        super(LabelRejected, self).__init__("%s: %r" % (reason, label))
        self.reason = reason
        self.label = label


def validate_label(label):
    """Return the NFC form of an acceptable label, or raise with a stable reason code."""
    if type(label) is not str:
        raise LabelRejected("not_a_string", label)
    norm = unicodedata.normalize("NFC", label)
    if norm == "":
        raise LabelRejected("empty", label)
    if norm in ("..", "."):
        raise LabelRejected("reserved_traversal", label)
    for ch in norm:
        cat = unicodedata.category(ch)
        if ord(ch) in BIDI:
            raise LabelRejected("bidi_control", label)
        if cat.startswith("C"):
            raise LabelRejected("control_character", label)
        if not (cat.startswith("L") or cat.startswith("N") or ch == " " or ch in ALLOWED_PUNCT):
            raise LabelRejected("illegal_character", label)
    if norm != norm.strip():
        raise LabelRejected("surrounding_whitespace", label)
    if norm.endswith(".") or norm.endswith(" "):
        raise LabelRejected("trailing_dot_or_space", label)
    if len(norm) > MAX_CODE_POINTS:
        raise LabelRejected("too_long", label)
    if len(norm.encode("utf-8")) > MAX_BYTES:
        raise LabelRejected("too_long", label)
    if _device_name(norm.split(".")[0]) in RESERVED_NAMES:
        raise LabelRejected("reserved_name", label)
    return norm


def _device_name(stem):
    """Windows answers to COM-superscript-1 as well as COM1, so fold every digit to ASCII."""
    out = []
    for ch in stem:
        d = unicodedata.digit(ch, None)
        out.append(str(d) if d is not None else ch)
    return "".join(out).upper()


def carried_form_ok(label):
    """The record must CARRY the NFC form, not merely normalise to it."""
    try:
        return validate_label(label) == label
    except LabelRejected:
        return False


def slug(label):
    """A deterministic, bounded path component. Distinct labels never merge."""
    norm = validate_label(label)
    body = re.sub(r"[^a-z0-9]+", "-", norm.casefold()).strip("-")[:SLUG_BODY]
    if not body:
        body = "label"
    tail = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:SLUG_HASH]
    return body + "-" + tail
