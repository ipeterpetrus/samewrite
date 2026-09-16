"""The history head, the ledger certificate and caller-supplied archive witnesses.

A head that could not be read and a head that does not exist are different values, as in phase 1R.
What changed is that each type has exactly one constructor, and the decoder calls it.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .canon import CanonMap
from .closed import Closed, ConstructionError
from .domains import Reason
from .values import (Digest, Epoch, ScopeDigests, ScopeId, ScopeSeqs, ShortDigest, WorkloadId,
                     seq_canon)

HEAD_SCHEMA_VERSION = 2
LEDGER_SCHEMA_VERSION = 2
LEDGER_COUNTERS = ("lines_total", "lines_rejected", "events_known", "events_unknown",
                   "writes_observed", "checked", "denied")


def _require(ok, reason, field, detail):
    if not ok:
        raise ConstructionError(reason, field, detail)


@dataclasses.dataclass(frozen=True, init=False)
class HeadEntry(Closed):
    scope: ScopeId
    highest_run_seq: int
    head_digest: Digest
    observation_count: int
    updated_at: Epoch

    def canon(self):
        return CanonMap([("scope_id", self.scope.text), ("highest_run_seq", self.highest_run_seq),
                         ("head_digest", self.head_digest.hex),
                         ("observation_count", self.observation_count),
                         ("updated_at", self.updated_at.seconds)])


@dataclasses.dataclass(frozen=True, init=False)
class HistoryHead(Closed):
    entries: typing.Tuple[HeadEntry, ...]

    def canon(self):
        return CanonMap([("schema_version", HEAD_SCHEMA_VERSION),
                         ("scopes", seq_canon(self.entries))])

    def entry_for(self, scope):
        """The entry, or KNOWN_ABSENT: the head was read and says nothing about this scope."""
        for entry in self.entries:
            if entry.scope == scope:
                return entry
        return Absence.KNOWN_ABSENT


@dataclasses.dataclass(frozen=True, init=False)
class LedgerCertificate(Closed):
    scope: ScopeId
    workload: WorkloadId
    host_profile_id: ShortDigest
    discovery_config_digest: Digest
    ledger_binding: Digest
    parser_contract_version: int
    lines_total: int
    lines_rejected: int
    events_known: int
    events_unknown: int
    writes_observed: int
    checked: int
    denied: int
    first_ts: typing.Union[Epoch, Absence]
    last_ts: typing.Union[Epoch, Absence]

    @property
    def is_empty(self):
        return (self.events_known + self.events_unknown) == 0

    def canon(self):
        first = self.first_ts.seconds if type(self.first_ts) is Epoch else None
        last = self.last_ts.seconds if type(self.last_ts) is Epoch else None
        pairs = [("cert_schema", LEDGER_SCHEMA_VERSION), ("scope_id", self.scope.text),
                 ("workload_class", self.workload.text),
                 ("host_profile_id", self.host_profile_id.hex),
                 ("discovery_config_digest", self.discovery_config_digest.hex),
                 ("ledger_binding", self.ledger_binding.hex),
                 ("parser_contract_version", self.parser_contract_version),
                 ("first_ts", first), ("last_ts", last)]
        pairs += [(name, getattr(self, name)) for name in LEDGER_COUNTERS]
        return CanonMap(pairs)


@dataclasses.dataclass(frozen=True, init=False)
class ArchiveWitness(Closed):
    """A VERIFIED archive, supplied by the caller. The rotation record alone cannot vouch."""
    archive_digest: Digest
    last_digests: ScopeDigests
    last_run_seqs: ScopeSeqs


@dataclasses.dataclass(frozen=True, init=False)
class ArchiveWitnesses(Closed):
    items: typing.Tuple[ArchiveWitness, ...]

    def lookup(self, archive_digest):
        for witness in self.items:
            if witness.archive_digest == archive_digest:
                return witness
        return Absence.KNOWN_ABSENT


def make_head_entry(scope, highest_run_seq, head_digest, observation_count, updated_at,
                    field="head entry"):
    R = Reason.HEAD_INVALID
    _require(type(scope) is ScopeId, R, field + ".scope_id", "a validated ScopeId")
    _require(f.is_nat(highest_run_seq), R, field + ".highest_run_seq", "a non-negative int")
    _require(type(head_digest) is Digest, R, field + ".head_digest", "a validated Digest")
    _require(f.is_nat(observation_count), R, field + ".observation_count",
             "a non-negative int")
    _require(type(updated_at) is Epoch, R, field + ".updated_at", "a validated Epoch")
    return HeadEntry._seal(scope=scope, highest_run_seq=highest_run_seq,
                           head_digest=head_digest, observation_count=observation_count,
                           updated_at=updated_at)


def make_head(entries, field="head"):
    """The head names each scope once. The ORDER of those entries is not evidence, so the head
    holds them in canonical scope order whatever order the caller supplied."""
    R = Reason.HEAD_INVALID
    _require(type(entries) is tuple, R, field + ".scopes", "a tuple")
    seen = set()
    for entry in entries:
        _require(type(entry) is HeadEntry, R, field + ".scopes", "a validated HeadEntry")
        _require(entry.scope.text not in seen, R, field + ".scopes",
                 "one entry per scope, got %r twice" % entry.scope.text)
        seen.add(entry.scope.text)
    return HistoryHead._seal(entries=tuple(sorted(entries, key=lambda e: e.scope.text)))


def make_ledger_certificate(scope, workload, host_profile_id, discovery_config_digest,
                            ledger_binding, parser_contract_version, counters, first_ts, last_ts,
                            field="ledger"):
    R = Reason.LEDGER_BAD_TYPE
    _require(type(scope) is ScopeId, R, field + ".scope_id", "a validated ScopeId")
    _require(type(workload) is WorkloadId, R, field + ".workload_class",
             "a validated WorkloadId")
    _require(type(host_profile_id) is ShortDigest, R, field + ".host_profile_id",
             "a validated ShortDigest")
    _require(type(discovery_config_digest) is Digest, R, field + ".discovery_config_digest",
             "a validated Digest")
    _require(type(ledger_binding) is Digest, R, field + ".ledger_binding", "a validated Digest")
    _require(f.is_nat(parser_contract_version), R, field + ".parser_contract_version",
             "a non-negative int")
    _require(type(counters) is dict and sorted(counters) == sorted(LEDGER_COUNTERS), R, field,
             "exactly the counters %s" % (sorted(LEDGER_COUNTERS),))
    for name in LEDGER_COUNTERS:
        _require(f.is_nat(counters[name]), R, field + "." + name, "a non-negative int")
    for name, value in (("first_ts", first_ts), ("last_ts", last_ts)):
        _require(type(value) is Epoch or value is Absence.KNOWN_ABSENT, R, field + "." + name,
                 "a validated Epoch, or KNOWN_ABSENT for an empty ledger")
    return LedgerCertificate._seal(scope=scope, workload=workload,
                                   host_profile_id=host_profile_id,
                                   discovery_config_digest=discovery_config_digest,
                                   ledger_binding=ledger_binding,
                                   parser_contract_version=parser_contract_version,
                                   first_ts=first_ts, last_ts=last_ts, **counters)


def make_archive_witness(archive_digest, last_digests, last_run_seqs, field="archive witness"):
    R = Reason.RECORD_SHAPE_INVALID
    _require(type(archive_digest) is Digest, R, field + ".archive_digest", "a validated Digest")
    _require(type(last_digests) is ScopeDigests, R, field + ".last_digests",
             "validated ScopeDigests")
    _require(type(last_run_seqs) is ScopeSeqs, R, field + ".last_run_seqs",
             "validated ScopeSeqs")
    return ArchiveWitness._seal(archive_digest=archive_digest, last_digests=last_digests,
                                last_run_seqs=last_run_seqs)


def make_archives(items, field="archives"):
    """A SET of witnesses: each archive once, in any order the caller supplies."""
    R = Reason.RECORD_SHAPE_INVALID
    _require(type(items) is tuple, R, field, "a tuple")
    seen = set()
    for witness in items:
        _require(type(witness) is ArchiveWitness, R, field, "a validated ArchiveWitness")
        _require(witness.archive_digest.hex not in seen, R, field,
                 "duplicate archive %r" % witness.archive_digest.hex)
        seen.add(witness.archive_digest.hex)
    return ArchiveWitnesses._seal(items=tuple(sorted(items,
                                                     key=lambda w: w.archive_digest.hex)))
