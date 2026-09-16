#!/usr/bin/env python3
"""The production history file, read and written through the frozen v1.4 evidence kernel.

Everything the kernel decides lives in `tools/evidence` and `tools/wire`, ported byte-for-byte.
What lives HERE is the part the kernel cannot know: which wire generations this repository has
actually written, and how a file that several agents append to at once is extended.

Two facts drive the whole module.

  THIS REPOSITORY'S LEGACY IS 0, 1 AND 2.  The frozen kernel ships a legacy reader for the
  generation its own fixtures used. SameWrite has written schema 0 (pre-1.2), 1 (population
  identity) and 2 (run/scope/quality) to real machines. Those are legacy HERE. The rule the
  kernel states about legacy is not touched and not weakened: a legacy record is read far enough
  to be counted and attributed, every fact its schema did not carry stays ABSENT, and a container
  holding one is UNVERIFIED — it can never gain current trust by defaulting.

  A CHAINED RECORD CANNOT BE WRITTEN BLIND.  A v1.4 record carries its position (`run_seq`) and
  the digest of the record before it. Two agents that both read the tail and then both append
  would write two records at one position, which the contract calls a duplicate position and
  which degrades the container. So the read-the-tail-and-append sequence is serialised with an
  advisory lock. Inside the lock the write is still ONE `write()` of one line, which is the
  property the existing append protocol rests on; the crash-fragment newline check is unchanged.
"""
import errno
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evidence.absence import Absence                                    # noqa: E402
from evidence.closed import ConstructionError                           # noqa: E402
from evidence.domains import Reason                                     # noqa: E402
from evidence.identity import record_digest                             # noqa: E402
from evidence.records import (SWEEP_TYPES, make_container, make_legacy_record,
                              make_rejection)                           # noqa: E402
from evidence.values import make_run_id, make_scope_id                  # noqa: E402
from wire.errors import WireError                                       # noqa: E402
from wire.record import decode_record                                   # noqa: E402

try:                                            # POSIX advisory locking; absent on some hosts
    import fcntl
except ImportError:                             # pragma: no cover - platform dependent
    fcntl = None

# The generations THIS repository has written. Extending this list is how a deployment tells the
# kernel what its own past looks like; it does not change what a legacy record is allowed to mean.
PRODUCTION_LEGACY_SCHEMAS = (0, 1, 2, 3)
MAX_RECORD = 1 << 20              # unchanged from the append protocol this file inherits


def _legacy_record(raw):
    """A previous-generation record, read only far enough to be counted and attributed.

    Missing `schema_version` IS generation 0: that is what a pre-1.2 record looks like, and
    treating it as an unreadable line would turn this repository's own history into damage.
    """
    if type(raw) is not dict:
        raise WireError(Reason.RECORD_SHAPE_INVALID, "legacy", "not an object")
    if "envelope" in raw:
        # It declares a CURRENT-generation envelope. Reaching here means the current decoder
        # refused it, and a record of this generation that does not decode is damage — not a
        # previous generation. Without this, a corrupt v1.4 record would quietly become a
        # schema-0 legacy record, because a top-level `schema_version` is absent in BOTH.
        raise WireError(Reason.RECORD_SHAPE_INVALID, "legacy",
                        "a current-generation record that did not decode is not legacy")
    version = raw.get("schema_version", 0)
    if type(version) is not int or isinstance(version, bool) \
            or version not in PRODUCTION_LEGACY_SCHEMAS:
        raise WireError(Reason.RECORD_UNSUPPORTED_SCHEMA, "legacy", "not a legacy schema")
    kind = Absence.UNVERIFIED                   # "carry_run" is not a v1.4 record kind
    scope = _soft(make_scope_id, raw.get("scope_id"))
    run_id = _soft(make_run_id, raw.get("run_id"))
    run_seq = raw.get("run_seq")
    if type(run_seq) is not int or isinstance(run_seq, bool) or run_seq < 0:
        run_seq = Absence.UNVERIFIED            # generations 0-2 carried no position
    try:
        return make_legacy_record(version, kind, scope, run_seq, run_id)
    except ConstructionError as exc:
        raise WireError(exc.reason, "legacy", str(exc))


def _soft(make, value):
    """Read a legacy field if it is readable; never invent one if it is not."""
    if value is None:
        return Absence.UNVERIFIED
    try:
        return make(value)
    except ConstructionError:
        return Absence.UNVERIFIED


def decode_line(raw):
    """-> ("current", record) | ("legacy", record). Raises WireError for a line that is neither."""
    try:
        return "current", decode_record(raw)
    except WireError:
        return "legacy", _legacy_record(raw)


def read_container(path):
    """The whole history file as ONE validated container: current, legacy and rejected lines.

    A line that decodes as neither generation does not disappear — it is a rejection, and the
    container reports it as damage.
    """
    records, legacy, rejections = [], [], []
    index = -1
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return make_container((), (), ())
    with handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:                        # blank lines are cosmetic; see carry.history
                continue
            try:
                raw = json.loads(line)
            except Exception:
                rejections.append(make_rejection(index, (Reason.LINE_UNPARSEABLE,)))
                continue
            try:
                generation, record = decode_line(raw)
            except WireError as exc:
                rejections.append(make_rejection(index, (exc.reason,)))
                continue
            (records if generation == "current" else legacy).append(record)
    return make_container(tuple(records), tuple(rejections), tuple(legacy))


def view_of(record):
    """A current record, rendered the way the 1.3 report reads a record.

    Shares are stored as COUNTS in v1.4 and reported as percentages: the percentage is derivable
    from the counts, the counts are not derivable from the percentages, so the wire keeps the
    thing that cannot be recovered. Per-bucket B/turn is not in the current record at all, so a
    comparison between two current records simply does not annotate it — an annotation that was
    never measured is worse than one that is missing.
    """
    payload, certificate = record.payload, record.certificate
    counts = {c.name: c.value for c in payload.shares.items}
    total = sum(counts.values())
    return {"schema_version": 4, "record_type": record.kind.value,
            "run_id": record.envelope.run_id.text, "run_seq": record.envelope.run_seq,
            "scope_id": record.envelope.scope.text,
            "workload_class": certificate.workload.text,
            "ts": payload.ts.seconds, "sessions": payload.sessions, "turns": payload.turns,
            "carry_bytes": payload.carry_bytes, "scanned": certificate.discovered,
            "shares": {k: round(100.0 * v / total, 4) for k, v in counts.items()} if total else {},
            "bpt": {}}


def read_views(path):
    """Every record in the file, in file order, as views the report can compare.

    Both generations are read. A legacy record is reported exactly as it was written — that is
    what makes a 1.3 machine still get a delta after the upgrade — and it carries no current
    trust: `history_integrity` over the same container says UNVERIFIED while any legacy record is
    in it, which is the fail-closed half of the same policy.
    """
    views = []
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return views
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except Exception:
                continue
            if type(raw) is not dict:
                continue
            try:
                record = decode_record(raw)
            except WireError:
                if isinstance(raw.get("shares"), dict):     # a 1.3 or earlier record
                    views.append(raw)
                continue
            if type(record) in SWEEP_TYPES:
                views.append(view_of(record))
    return views


def tail_for_scope(container, scope):
    """-> (next_run_seq, prev_digest_or_absence) for the next record of this scope.

    Position is per scope, because the chain is per scope: two scopes in one file are two
    histories that happen to share a container.
    """
    in_scope = container.in_scope(scope)     # events chain too: position belongs to the record
    if not in_scope:
        return 0, Absence.KNOWN_ABSENT
    newest = max(in_scope, key=lambda r: r.envelope.run_seq)
    return newest.envelope.run_seq + 1, record_digest(newest)


def _lock(handle):
    if fcntl is None:                           # pragma: no cover - platform dependent
        return False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return True
    except OSError as exc:                      # a filesystem without locking: proceed unlocked
        if exc.errno in (errno.ENOLCK, errno.EINVAL, errno.EOPNOTSUPP, errno.EACCES):
            return False
        raise


def _unlock(handle):
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:                         # pragma: no cover - released on close anyway
            pass


def append_chained(path, build, scope):
    """Append ONE current-generation record, positioned and chained under an exclusive lock.

    `build(run_seq, prev)` returns the raw wire object for the record. It is called INSIDE the
    lock, because the position it is given must still be the tail when the line is written.

    -> (ok, note). The note is for a human; nothing here raises on a filesystem that refuses.
    """
    try:
        handle = open(path, "a+", encoding="utf-8")
    except OSError as exc:
        return False, "history unwritable (%s)" % exc.__class__.__name__
    with handle:
        locked = _lock(handle)
        try:
            container = read_container(path)
            run_seq, prev = tail_for_scope(container, scope)
            raw = build(run_seq, prev)
            line = json.dumps(raw, ensure_ascii=False, sort_keys=True) + "\n"
            if len(line.encode("utf-8")) > MAX_RECORD:
                return False, "record too large to append safely — not written"
            # A machine that died mid-append leaves a line with no newline. Appending straight
            # after it would GLUE this record to the fragment and destroy a good record as well
            # as the torn one. Unchanged from the protocol this file inherits.
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(handle.tell() - 1)
                if handle.read(1) != "\n":
                    handle.write("\n")
                handle.seek(0, os.SEEK_END)
            handle.write(line)
            handle.flush()
            return True, "run_seq=%d" % run_seq
        except OSError:
            return False, "history unwritable"
        finally:
            if locked:
                _unlock(handle)
