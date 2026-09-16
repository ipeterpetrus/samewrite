"""Decoders for the history head, the ledger certificate and archive witnesses."""
from evidence.absence import Absence
from evidence.containers import (HEAD_SCHEMA_VERSION, LEDGER_COUNTERS, LEDGER_SCHEMA_VERSION,
                                 make_archive_witness, make_archives, make_head, make_head_entry,
                                 make_ledger_certificate)
from evidence.domains import Reason
from evidence.values import (make_digest, make_epoch, make_scope_digests, make_scope_id,
                             make_scope_seqs, make_short_digest, make_workload_id)
from . import parse as P

HEAD_ENTRY_FIELDS = ("scope_id", "highest_run_seq", "head_digest", "observation_count",
                     "updated_at")
LEDGER_FIELDS = ("cert_schema", "scope_id", "workload_class", "host_profile_id",
                 "discovery_config_digest", "ledger_binding", "parser_contract_version",
                 "first_ts", "last_ts") + LEDGER_COUNTERS
WITNESS_FIELDS = ("archive_digest", "last_digests", "last_run_seqs")


def decode_head(raw, path="head"):
    body = P.members(raw, path, ("schema_version", "scopes"), Reason.HEAD_INVALID)
    P.schema_version(body["schema_version"], path + ".schema_version", HEAD_SCHEMA_VERSION,
                     Reason.HEAD_INVALID)
    entries = []
    for i, entry in enumerate(P.array(body["scopes"], path + ".scopes", Reason.HEAD_INVALID)):
        at = "%s.scopes[%d]" % (path, i)
        fields = P.members(entry, at, HEAD_ENTRY_FIELDS, Reason.HEAD_INVALID)
        entries.append(P.built(at, make_head_entry,
                               P.built(at, make_scope_id, fields["scope_id"], "scope_id",
                                       Reason.HEAD_INVALID),
                               fields["highest_run_seq"],
                               P.built(at, make_digest, fields["head_digest"], "head_digest",
                                       Reason.HEAD_INVALID),
                               fields["observation_count"],
                               P.built(at, make_epoch, fields["updated_at"], "updated_at",
                                       Reason.HEAD_INVALID)))
    return P.built(path, make_head, tuple(entries))


def decode_ledger_certificate(raw, path="ledger"):
    body = P.members(raw, path, LEDGER_FIELDS, Reason.LEDGER_MISSING_KEY)
    P.schema_version(body["cert_schema"], path + ".cert_schema", LEDGER_SCHEMA_VERSION,
                     Reason.CERT_UNSUPPORTED_SCHEMA)
    stamps = {}
    for name in ("first_ts", "last_ts"):
        value = body[name]
        stamps[name] = (Absence.KNOWN_ABSENT if value is None
                        else P.built(path, make_epoch, value, name, Reason.LEDGER_BAD_TYPE))
    return P.built(path, make_ledger_certificate,
                   P.built(path, make_scope_id, body["scope_id"]),
                   P.built(path, make_workload_id, body["workload_class"]),
                   P.built(path, make_short_digest, body["host_profile_id"], "host_profile_id",
                           Reason.LEDGER_BAD_TYPE),
                   P.built(path, make_digest, body["discovery_config_digest"],
                           "discovery_config_digest", Reason.LEDGER_BAD_TYPE),
                   P.built(path, make_digest, body["ledger_binding"], "ledger_binding",
                           Reason.LEDGER_BAD_TYPE),
                   body["parser_contract_version"],
                   {name: body[name] for name in LEDGER_COUNTERS},
                   stamps["first_ts"], stamps["last_ts"])


def decode_archives(raw, path="archives"):
    items = []
    for i, entry in enumerate(P.array(raw, path)):
        at = "%s[%d]" % (path, i)
        fields = P.members(entry, at, WITNESS_FIELDS)
        digests = tuple((scope, P.built(at, make_digest, value, "last_digests"))
                        for scope, value in P.mapping(fields["last_digests"],
                                                      at + ".last_digests"))
        items.append(P.built(at, make_archive_witness,
                             P.built(at, make_digest, fields["archive_digest"],
                                     "archive_digest"),
                             P.built(at, make_scope_digests, digests, "last_digests"),
                             P.built(at, make_scope_seqs,
                                     P.mapping(fields["last_run_seqs"], at + ".last_run_seqs"),
                                     "last_run_seqs")))
    return P.built(path, make_archives, tuple(items))
