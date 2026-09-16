"""Validated scalar and small composite values, each with ONE constructor.

Every function here owns the complete invariant of the type it returns. The wire decoder calls
these; so does any algorithm that derives a new value. There is no second place where a Digest
decides what a Digest is.
"""
import dataclasses
import typing

from . import forms as f
from .canon import CanonMap, CanonSeq, sha256_hex
from .closed import Closed, ConstructionError
from .domains import Reason


def _fail(reason, field, detail):
    raise ConstructionError(reason, field, detail)


def _require(ok, reason, field, detail):
    if not ok:
        _fail(reason, field, detail)


@dataclasses.dataclass(frozen=True, init=False)
class Digest(Closed):
    """sha256, 64 lowercase hex characters."""
    hex: str

    def canon(self):
        return self.hex

    def __repr__(self):
        return "Digest(%s...)" % self.hex[:12]


@dataclasses.dataclass(frozen=True, init=False)
class ShortDigest(Closed):
    """A 16-hex host profile identifier. Never interchangeable with a content digest."""
    hex: str

    def canon(self):
        return self.hex


@dataclasses.dataclass(frozen=True, init=False)
class PathDigest(Closed):
    """A 12-hex privacy-preserving path name."""
    hex: str

    def canon(self):
        return self.hex


@dataclasses.dataclass(frozen=True, init=False)
class WorldIdCore(Closed):
    """Identity of the SUBJECT: scope, workload, discovery config, parser contract."""
    hex: str

    def canon(self):
        return self.hex


@dataclasses.dataclass(frozen=True, init=False)
class WorldId(Closed):
    """Identity of the subject AS SAMPLED. Carrying one where the other belongs was finding 25."""
    hex: str

    def canon(self):
        return self.hex


@dataclasses.dataclass(frozen=True, init=False)
class SampleId(Closed):
    """Identity of the frozen file set."""
    hex: str

    def canon(self):
        return self.hex


@dataclasses.dataclass(frozen=True, init=False)
class RunId(Closed):
    text: str

    def canon(self):
        return self.text

    def __repr__(self):
        return "RunId(%s)" % self.text[:8]


@dataclasses.dataclass(frozen=True, init=False)
class ScopeId(Closed):
    """A validated label CARRYING its NFC form (section 12)."""
    text: str

    def canon(self):
        return self.text

    def __repr__(self):
        return "ScopeId(%r)" % self.text


@dataclasses.dataclass(frozen=True, init=False)
class WorkloadId(Closed):
    """The workload class. The contract says: required, and MAY BE "".

    It is not a path label: `scope_id` names a directory and carries section 12's rules, and
    phase 1R wrongly gave those rules to this field too, which refused a value the contract
    explicitly permits. An empty workload is PRESENT with the value "", never an absence.
    """
    text: str

    @property
    def is_empty(self):
        return self.text == ""

    def canon(self):
        return self.text


@dataclasses.dataclass(frozen=True, init=False)
class FindingId(Closed):
    """A finding named in the registry: a finding with no entry has no floors, so it has no id."""
    text: str

    def canon(self):
        return self.text

    def __repr__(self):
        return "FindingId(%s)" % self.text


@dataclasses.dataclass(frozen=True, init=False)
class CandidateId(Closed):
    text: str

    def canon(self):
        return self.text


@dataclasses.dataclass(frozen=True, init=False)
class Epoch(Closed):
    seconds: int

    def canon(self):
        return self.seconds

    def __repr__(self):
        return "Epoch(%d)" % self.seconds


@dataclasses.dataclass(frozen=True, init=False)
class OrderKey(Closed):
    """A position in one history: (run_seq, run_id), total and byte-exact."""
    run_seq: int
    run_id: RunId

    def canon(self):
        return CanonSeq([self.run_seq, self.run_id.text])

    def _sort(self):
        return (self.run_seq, self.run_id.text.encode("utf-8"))

    def __lt__(self, other):
        if type(other) is not OrderKey:
            return NotImplemented
        return self._sort() < other._sort()

    def __le__(self, other):
        if type(other) is not OrderKey:
            return NotImplemented
        return self._sort() <= other._sort()

    def __gt__(self, other):
        if type(other) is not OrderKey:
            return NotImplemented
        return self._sort() > other._sort()

    def __ge__(self, other):
        if type(other) is not OrderKey:
            return NotImplemented
        return self._sort() >= other._sort()

    def __repr__(self):
        return "OrderKey(%d, %s)" % (self.run_seq, self.run_id.text[:8])


@dataclasses.dataclass(frozen=True, init=False)
class NamedCount(Closed):
    name: str
    value: int


@dataclasses.dataclass(frozen=True, init=False)
class NamedCounts(Closed):
    """A set of named non-negative counts, unique by name and held in canonical name order.

    The ORDER the caller supplies is not evidence: a JSON object's members have no semantic
    order, and the canonical encoder sorts keys anyway. Uniqueness IS evidence, so that is what
    this checks (Review B, B8).
    """
    items: typing.Tuple[NamedCount, ...]

    def canon(self):
        return CanonMap([(c.name, c.value) for c in self.items])

    def __len__(self):
        return len(self.items)

    def get(self, name):
        for c in self.items:
            if c.name == name:
                return c.value
        return None

    @property
    def is_empty(self):
        return not self.items


@dataclasses.dataclass(frozen=True, init=False)
class ScopeDigest(Closed):
    scope: ScopeId
    digest: Digest


@dataclasses.dataclass(frozen=True, init=False)
class ScopeDigests(Closed):
    items: typing.Tuple[ScopeDigest, ...]

    def canon(self):
        return CanonMap([(e.scope.text, e.digest.hex) for e in self.items])

    def lookup(self, scope):
        for e in self.items:
            if e.scope == scope:
                return e.digest
        return None


@dataclasses.dataclass(frozen=True, init=False)
class ScopeSeq(Closed):
    scope: ScopeId
    run_seq: int


@dataclasses.dataclass(frozen=True, init=False)
class ScopeSeqs(Closed):
    items: typing.Tuple[ScopeSeq, ...]

    def canon(self):
        return CanonMap([(e.scope.text, e.run_seq) for e in self.items])

    def lookup(self, scope):
        for e in self.items:
            if e.scope == scope:
                return e.run_seq
        return None


@dataclasses.dataclass(frozen=True, init=False)
class SourceId(Closed):
    """A.3 stable source identity, frozen at selection time."""
    path: PathDigest
    dev: int
    inode: int
    size: int
    mtime_ns: int

    def canon(self):
        return CanonMap([("path_digest", self.path.hex), ("dev", self.dev),
                         ("inode", self.inode), ("size", self.size),
                         ("mtime_ns", self.mtime_ns)])


@dataclasses.dataclass(frozen=True, init=False)
class ManifestEntry(Closed):
    """One file actually read: which path, and the bytes that were read from it."""
    path: PathDigest
    content: Digest

    def canon(self):
        return CanonMap([("path_digest", self.path.hex), ("content_digest", self.content.hex)])


# --- the authoritative constructors. One per type, and the only way any of them is built.

def _checked_hex(text, width, field, reason):
    """Validate a fixed-width hex string. A predicate, not an authority: it allocates nothing."""
    _require(f.is_str(text), reason, field, "a digest is a string")
    _require(f.hex_of(width)(text), reason, field, "%d lowercase hex characters" % width)
    return text


def make_digest(text, field="digest", reason=Reason.CERT_BAD_TYPE):
    return Digest._seal(hex=_checked_hex(text, 64, field, reason))


def make_short_digest(text, field="host_profile_id", reason=Reason.CERT_BAD_TYPE):
    return ShortDigest._seal(hex=_checked_hex(text, 16, field, reason))


def make_path_digest(text, field="path_digest", reason=Reason.CERT_BAD_TYPE):
    return PathDigest._seal(hex=_checked_hex(text, 12, field, reason))


def make_world_id(text, field="world_id", reason=Reason.CERT_BAD_TYPE):
    return WorldId._seal(hex=_checked_hex(text, 64, field, reason))


def make_world_id_core(text, field="world_id_core", reason=Reason.CERT_BAD_TYPE):
    return WorldIdCore._seal(hex=_checked_hex(text, 64, field, reason))


def make_sample_id(text, field="sample_id", reason=Reason.CERT_BAD_TYPE):
    return SampleId._seal(hex=_checked_hex(text, 64, field, reason))


def make_run_id(text, field="run_id", reason=Reason.ENVELOPE_BAD_TYPE):
    _require(f.is_uuid4(text), reason, field, "a lowercase version-4 UUID")
    return RunId._seal(text=text)


def make_scope_id(text, field="scope_id", reason=Reason.PATH_LABEL_REJECTED):
    _require(f.is_carried_label(text), reason, field,
             "the value must CARRY the validated NFC form of its label")
    return ScopeId._seal(text=text)


def make_workload_id(text, field="workload_class", reason=Reason.CERT_BAD_TYPE):
    """A required string that may be empty. Missing is a different fact, and the closed member
    set of every object that holds one is what establishes that it is present at all."""
    _require(f.is_str(text), reason, field,
             "a string; the empty string is a valid workload class")
    return WorkloadId._seal(text=text)


def make_finding_id(text, field="finding_id", reason=Reason.ARTIFACT_INTERNAL_MISMATCH):
    """The registry is CLOSED: a finding with no entry has no floors, so it has no identity.

    This rule lived only in the wire decoder in phase 1R, which let an internal caller mint a
    FindingId naming a finding that does not exist (Review B, B3). It lives here now, once.
    """
    from .registry import FINDING_FLOORS
    _require(f.is_identifier(text), reason, field, "an identifier, ASCII and without spaces")
    _require(text in FINDING_FLOORS, reason, field,
             "no registry entry for %r; a missing floor is never a default" % (text,))
    return FindingId._seal(text=text)


def make_candidate_id(text, field="candidate_id", reason=Reason.ARTIFACT_INTERNAL_MISMATCH):
    _require(f.is_identifier(text), reason, field, "an identifier, ASCII and without spaces")
    return CandidateId._seal(text=text)


def make_epoch(seconds, field="epoch", reason=Reason.CERT_BAD_TYPE):
    _require(f.is_nat(seconds), reason, field, "epoch seconds, a non-negative int")
    return Epoch._seal(seconds=seconds)


def make_order_key(run_seq, run_id, field="order_key", reason=Reason.CERT_BAD_TYPE):
    _require(f.is_nat(run_seq), reason, field + ".run_seq", "a position is never negative")
    _require(type(run_id) is RunId, reason, field + ".run_id", "a validated RunId")
    return OrderKey._seal(run_seq=run_seq, run_id=run_id)


def make_named_counts(pairs, field="counts", reason=Reason.PAYLOAD_BAD_TYPE):
    """Named non-negative counts. Any member order is accepted; duplicates are not."""
    _require(type(pairs) is tuple, reason, field, "a tuple of (name, value) pairs")
    seen, items = set(), []
    for pair in pairs:
        _require(type(pair) is tuple and len(pair) == 2, reason, field, "a (name, value) pair")
        name, value = pair
        _require(f.is_str(name), reason, field, "a count name is a string")
        _require(f.is_nat(value), reason, field + "." + str(name),
                 "a count is a non-negative int")
        _require(name not in seen, reason, field, "duplicate count name %r" % (name,))
        seen.add(name)
        items.append(NamedCount._seal(name=name, value=value))
    items.sort(key=lambda c: c.name)
    return NamedCounts._seal(items=tuple(items))


def _checked_pairs(pairs, field, reason, value_check, value_detail):
    """Validate a scope-keyed map and return (scope, value) in canonical scope order.

    The member ORDER a caller supplies is not evidence; a duplicate scope is.
    """
    _require(type(pairs) is tuple, reason, field, "a tuple of (scope, value) pairs")
    seen, out = set(), []
    for pair in pairs:
        _require(type(pair) is tuple and len(pair) == 2, reason, field, "a (scope, value) pair")
        scope_text, value = pair
        scope = make_scope_id(scope_text, field + " key", reason)
        _require(value_check(value), reason, field + "." + scope.text, value_detail)
        _require(scope.text not in seen, reason, field, "duplicate scope %r" % (scope.text,))
        seen.add(scope.text)
        out.append((scope, value))
    out.sort(key=lambda e: e[0].text)
    return out


def make_scope_digests(pairs, field="scope_digests", reason=Reason.RECORD_SHAPE_INVALID):
    checked = _checked_pairs(pairs, field, reason, lambda v: type(v) is Digest,
                             "a validated Digest")
    items = tuple(ScopeDigest._seal(scope=scope, digest=value) for scope, value in checked)
    return ScopeDigests._seal(items=items)


def make_scope_seqs(pairs, field="scope_seqs", reason=Reason.RECORD_SHAPE_INVALID):
    checked = _checked_pairs(pairs, field, reason, f.is_nat, "a position is never negative")
    items = tuple(ScopeSeq._seal(scope=scope, run_seq=value) for scope, value in checked)
    return ScopeSeqs._seal(items=items)


def make_source_id(path, dev, inode, size, mtime_ns, field="stable_source_id",
                   reason=Reason.FROZEN_SELECTION_INVALID):
    _require(type(path) is PathDigest, reason, field + ".path_digest", "a validated PathDigest")
    for name, value in (("dev", dev), ("inode", inode), ("mtime_ns", mtime_ns)):
        _require(f.is_int(value), reason, field + "." + name, "an int")
    _require(f.is_nat(size), reason, field + ".size", "a non-negative int")
    return SourceId._seal(path=path, dev=dev, inode=inode, size=size, mtime_ns=mtime_ns)


def make_manifest_entry(path, content, field="sample_manifest entry",
                        reason=Reason.PAYLOAD_BAD_TYPE):
    _require(type(path) is PathDigest, reason, field + ".path_digest", "a validated PathDigest")
    _require(type(content) is Digest, reason, field + ".content_digest", "a validated Digest")
    return ManifestEntry._seal(path=path, content=content)


def digest_of(value):
    """The Digest of a canonical form or of any validated object that renders one."""
    form = value.canon() if hasattr(value, "canon") else value
    return make_digest(sha256_hex(form), "derived digest")


def seq_canon(items):
    _require(type(items) is tuple, Reason.RECORD_SHAPE_INVALID, "sequence",
             "a tuple of validated values")
    for item in items:
        _require(isinstance(item, Closed), Reason.RECORD_SHAPE_INVALID, "sequence",
                 "a tuple of validated values")
    return CanonSeq([i.canon() for i in items])
