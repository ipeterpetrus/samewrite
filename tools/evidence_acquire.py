#!/usr/bin/env python3
"""Turn what the scan actually observed into a TYPED v1.4 observation.

The rule this module exists to obey: production never assembles a current-schema JSON object and
assumes it is valid. Raw acquisition facts go into the frozen constructors, the constructors
decide whether they are evidence, and the canonical encoder produces the bytes. If the facts do
not add up — the accounting law, the manifest subset rule, the conservation rules — the record is
still written, and it is written UNVERIFIED. The one thing that cannot happen is a record that
looks clean because the producer skipped a check the reader performs.

    filesystem/transcript observation
            v
    raw acquisition facts            (carry.accumulate: outcomes, counters, per-file identity)
            v
    authoritative constructors       (evidence/*, one per semantic type)
            v
    typed evidence values            (CarrySweep | CarrySweepFailed)
            v
    canonical current wire encoding  (wire/encode.py)

PRIVACY. A path never leaves this module. What is carried is `path_digest` — twelve hex
characters of a digest over the absolute path — and `content_digest`, a digest over the bytes
that were read. Neither can be turned back into a path or a transcript, and the discovery config
carries the root as a digest and the include/exclude patterns as SHAPES, never as a path.
"""
import hashlib
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evidence.absence import Absence                                    # noqa: E402
from evidence.certificate import evaluate_observation                   # noqa: E402
from evidence.domains import SamplePolicy                               # noqa: E402
from evidence.identity import discovery_config_digest, host_profile_id  # noqa: E402
from evidence.preimages import make_discovery_config, make_host_profile  # noqa: E402
from evidence.records import (make_carry_sweep, make_carry_sweep_failed, make_certificate,
                              make_envelope, make_payload)              # noqa: E402
from evidence.values import (make_digest, make_epoch, make_manifest_entry, make_named_counts,
                             make_path_digest, make_run_id, make_scope_id, make_source_id,
                             make_workload_id)                          # noqa: E402
from wire import encode as wire_encode                                  # noqa: E402

PARSER_CONTRACT_VERSION = 1       # the carry transcript parser this build ships
CONFIG_SCHEMA = 1                 # discovery config preimage generation


def new_run_id():
    """Opaque, collision-resistant, carries nothing about the machine or the user.

    A lowercase version-4 UUID, which is what `make_run_id` accepts: the identity a record is
    written with is the identity the reader validates, with no second spelling in between.
    """
    return str(uuid.uuid4())


def path_digest_of(path):
    """Twelve hex characters over the absolute path. The path itself never leaves this function."""
    return hashlib.sha256(os.path.abspath(path).encode("utf-8", "surrogateescape")).hexdigest()[:12]


def source_of(path, facts):
    """One selected source, as the contract identifies it: digest of the path, plus the identity
    the filesystem gave it at selection time."""
    return make_source_id(make_path_digest(path_digest_of(path)),
                          int(facts["dev"]), int(facts["inode"]),
                          int(facts["size"]), int(facts["mtime_ns"]))


def host_profile():
    """Facts about THIS host that decide whether two observations are comparable at all.

    Never a hostname, a user, or a path: the platform family, the interpreter's major.minor, the
    separator and the case behaviour of the target filesystem.
    """
    home = os.path.expanduser("~")
    case_sensitive = "sensitive"
    try:
        case_sensitive = "insensitive" if os.path.exists(home.upper()) and \
            os.path.exists(home.lower()) and home.upper() != home.lower() else "sensitive"
    except OSError:                                             # pragma: no cover
        case_sensitive = "unknown"
    return make_host_profile(sys.platform,
                             "%d.%d" % (sys.version_info[0], sys.version_info[1]),
                             "unknown",              # portable filesystem type is not knowable
                             os.sep, case_sensitive)


def discovery_config(roots, include, exclude, max_depth=-1, max_file_bytes=0,
                     follow_symlinks=False):
    """The discovery this run performed, as a digest preimage.

    `roots` are hashed, never carried. `include`/`exclude` are SHAPES ("*.jsonl"), never the
    paths a caller typed: a user-supplied glob can contain a directory name, and a directory name
    is exactly the thing this repository promises never to write down.
    """
    joined = "\n".join(sorted(os.path.abspath(r) for r in roots))
    root = make_digest(hashlib.sha256(joined.encode("utf-8", "surrogateescape")).hexdigest())
    return make_discovery_config(CONFIG_SCHEMA, root, tuple(include), tuple(exclude),
                                 int(max_depth), int(max_file_bytes), bool(follow_symlinks))


def certificate_for(facts, scope_id, workload_class, writer_version, config, profile,
                    completed_at):
    """The acquisition certificate: what this sweep attempted, reached and lost."""
    sources = tuple(sorted((source_of(p, f) for p, f in facts["sources"].items()),
                           key=lambda s: s.path.hex))
    bound = facts.get("sample_bound")
    policy = SamplePolicy.NEWEST_N if bound else SamplePolicy.ALL
    counters = {name: int(facts["counters"].get(name, 0)) for name in
                ("discovered", "skipped_by_limit", "unreadable", "oversize", "identity_changed",
                 "empty_source", "not_attempted", "malformed", "records_rejected",
                 "dirs_unreadable")}
    return make_certificate(
        make_workload_id(str(workload_class or "")),
        policy,
        int(bound) if bound else Absence.KNOWN_ABSENT,
        sources,
        discovery_config_digest(config),
        PARSER_CONTRACT_VERSION,
        host_profile_id(profile),
        str(writer_version or ""),
        make_epoch(int(completed_at)),
        Absence.KNOWN_ABSENT,           # this producer asserts NOTHING: the reader derives it
        counters)


def payload_for(facts, when):
    """The measurement, and the manifest of what was actually read."""
    manifest = tuple(sorted(
        (make_manifest_entry(make_path_digest(path_digest_of(p)), make_digest(f["content"]))
         for p, f in facts["parsed"].items()), key=lambda e: e.path.hex))
    shares = make_named_counts(tuple((str(k), int(v)) for k, v in sorted(facts["carry"].items())))
    turns = int(facts["turns"])
    total = int(facts.get("carry_total", sum(facts["carry"].values())))
    return make_payload(shares, (total // turns) if turns else 0, make_epoch(int(when)),
                        int(facts["sessions"]), turns, total, manifest)


def observation(facts, scope_id, workload_class, writer_version, run_seq, prev, when,
                run_id=None, roots=(), include=("*.jsonl",), exclude=()):
    """The typed observation for this sweep: a measurement, or a tombstone when nothing parsed.

    A failed sweep is a DIFFERENT TYPE, not a sweep with zeros: `CarrySweepFailed` cannot carry a
    share or a count, so a failure cannot be dressed up as a quiet measurement.
    """
    envelope = make_envelope(make_run_id(run_id or new_run_id()), make_scope_id(str(scope_id)),
                             int(run_seq), prev)
    config, profile = discovery_config(roots, include, exclude), host_profile()
    certificate = certificate_for(facts, scope_id, workload_class, writer_version, config,
                                  profile, when)
    if facts["parsed"]:
        return make_carry_sweep(envelope, payload_for(facts, when), certificate)
    empty = make_payload(make_named_counts(()), 0, make_epoch(int(when)), 0, 0, 0, ())
    return make_carry_sweep_failed(envelope, empty, certificate)


def encoded(record):
    """The canonical current-generation wire object for this record."""
    return wire_encode.record(record)


def state_of(record, now):
    """What a READER derives from this record, computed with the reader's own function."""
    return evaluate_observation(record, make_epoch(int(now)))
