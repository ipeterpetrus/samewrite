"""Section 7 + B.4 - identity is not equivalence, over typed observations.

Review B (B7) found the retry representative still depended on input order when two copies shared
a position and differed only in `prev_digest`: the selector replaced the incumbent only for a
STRICTLY greater order key, so first-seen won every tie. The rule here is total and explicit --
newest position, then the record digest -- so a multiset has one representative whatever order the
reader walked it in.
"""
import dataclasses
import typing

from . import forms as f
from .absence import Absence
from .certificate import MIN_PLAUSIBLE_EPOCH, evaluate_observation
from .closed import Closed, ConstructionError
from .domains import AcquisitionIntegrity, DomainError, Reason, require
from .identity import (canonical_newest, canonical_order, observation_identity,
                       record_digest)
from .records import SWEEP_TYPES, ValidatedContainer
from .values import Epoch, RunId, ScopeId, make_epoch


class Outcome(object):
    SINGLE = "SINGLE"
    RETRY = "RETRY"
    CONFLICT = "CONFLICT"


OUTCOMES = (Outcome.SINGLE, Outcome.RETRY, Outcome.CONFLICT)


@dataclasses.dataclass(frozen=True, init=False)
class Group(Closed):
    """One observation identity and everything the batch said under it.

    There is no stored integrity: it is a function of the members AND of the clock the caller
    evaluates against, so storing it created a field that could contradict its own members
    (Review B, B6). It is derived on demand instead.
    """
    run_id: RunId
    scope: ScopeId
    members: typing.Tuple[object, ...]
    outcome: str
    used: typing.Union[object, Absence]

    def integrity_at(self, now):
        """The worst effective integrity among the members, as of `now`."""
        return AcquisitionIntegrity.worst(*[evaluate_observation(m, now=now).effective
                                            for m in self.members])


@dataclasses.dataclass(frozen=True, init=False)
class DedupResult(Closed):
    groups: typing.Tuple[Group, ...]
    usable: typing.Tuple[object, ...]
    conflicts: int
    retries: int
    reasons: typing.Tuple[Reason, ...]
    unreadable: int


def _need(ok, field, detail):
    if not ok:
        raise ConstructionError(Reason.DEDUP_CONFLICT, field, detail)


def make_group(run_id, scope, members, outcome, used, field="group"):
    """A group is not a bag of fields: the outcome, the members and the representative are one
    fact stated three ways, and the constructor owns the relation between them (Review A, A8)."""
    _need(type(run_id) is RunId, field + ".run_id", "a validated RunId")
    _need(type(scope) is ScopeId, field + ".scope", "a validated ScopeId")
    _need(type(members) is tuple and members, field + ".members", "a non-empty tuple")
    for member in members:
        _need(type(member) in SWEEP_TYPES, field + ".members", "validated sweeps")
        _need(observation_identity(member) == (run_id, scope), field + ".members",
              "every member shares the group's identity")
    _need(outcome in OUTCOMES, field + ".outcome", "one of %s" % (OUTCOMES,))
    # a multiset has ONE arrangement, so two readings of the same batch produce equal groups
    _need(members == canonical_order(members), field + ".members",
          "members are held in canonical order, not in the order they were read")
    equivalences = {m.equivalence() for m in members}
    if outcome == Outcome.SINGLE:
        _need(len(members) == 1, field + ".members", "a SINGLE group holds one observation")
        _need(used is members[0], field + ".used", "the single member is the representative")
    elif outcome == Outcome.RETRY:
        _need(len(members) > 1, field + ".members", "a RETRY group holds more than one copy")
        _need(len(equivalences) == 1, field + ".members",
              "a RETRY group's members are the same observation")
        _need(any(used is m for m in members), field + ".used", "the representative is a member")
        _need(used is canonical_representative(members), field + ".used",
              "the representative is the canonical one, not a chosen one")
    else:
        _need(len(members) > 1, field + ".members", "a CONFLICT group holds more than one claim")
        _need(len(equivalences) > 1, field + ".members",
              "a CONFLICT group's members disagree")
        _need(used is Absence.KNOWN_ABSENT, field + ".used",
              "a conflicted group has no usable member")
    return Group._seal(run_id=run_id, scope=scope, members=members, outcome=outcome, used=used)


def make_dedup_result(groups, usable, conflicts, retries, reasons, unreadable,
                      field="dedup_result"):
    """Every summary field is DERIVED from the groups, so a result cannot disagree with the
    groups it summarises (Review A, A9)."""
    _need(type(groups) is tuple and all(type(g) is Group for g in groups), field + ".groups",
          "a tuple of validated groups")
    _need(type(usable) is tuple and all(type(u) in SWEEP_TYPES for u in usable),
          field + ".usable", "a tuple of validated sweeps")
    for name, value in (("conflicts", conflicts), ("retries", retries),
                        ("unreadable", unreadable)):
        _need(f.is_nat(value), field + "." + name, "a non-negative int")
    _need(type(reasons) is tuple and all(type(r) is Reason for r in reasons), field + ".reasons",
          "a tuple of reason codes")
    identities = [(g.run_id.text, g.scope.text) for g in groups]
    _need(len(set(identities)) == len(identities), field + ".groups",
          "one group per observation identity")
    _need(identities == sorted(identities), field + ".groups",
          "groups are held in canonical identity order, so a permuted batch reads the same")
    expected_conflicts = sum(1 for g in groups if g.outcome == Outcome.CONFLICT)
    expected_retries = sum(1 for g in groups if g.outcome == Outcome.RETRY)
    expected_usable = tuple(g.used for g in groups if g.outcome != Outcome.CONFLICT)
    _need(conflicts == expected_conflicts, field + ".conflicts",
          "%d conflicted groups, not %d" % (expected_conflicts, conflicts))
    _need(retries == expected_retries, field + ".retries",
          "%d retry groups, not %d" % (expected_retries, retries))
    _need(len(usable) == len(expected_usable)
          and all(a is b for a, b in zip(usable, expected_usable)), field + ".usable",
          "the usable set IS the representatives of the unconflicted groups")
    _need((Reason.DEDUP_CONFLICT in reasons) == (expected_conflicts > 0), field + ".reasons",
          "a conflict is reported when and only when there is one")
    _need((Reason.RECORD_UNREADABLE in reasons) == (unreadable > 0), field + ".reasons",
          "an unreadable line is reported when and only when there is one")
    return DedupResult._seal(groups=groups, usable=usable, conflicts=conflicts, retries=retries,
                             reasons=reasons, unreadable=unreadable)


def canonical_representative(members):
    """The one member a multiset of identical observations is represented by.

    One rule, defined once in `identity.canonical_newest`: newest position, then the record
    digest. Never first-seen.
    """
    if type(members) is not tuple or not members:
        raise DomainError("a representative is chosen from a non-empty tuple of sweeps")
    for member in members:
        if type(member) not in SWEEP_TYPES:
            raise DomainError("a representative is chosen from validated sweeps, got %r"
                              % type(member).__name__)
    return canonical_newest(members)


def _default_now(records):
    stamps = [r.certificate.completed_at.seconds for r in records]
    return make_epoch(max(stamps) if stamps else MIN_PLAUSIBLE_EPOCH, "now")


def newest_completed_at(container):
    """The newest completion stamp in a batch. A caller that wants this as its clock asks for it
    explicitly; `dedup` no longer defaults one behind the caller's back (Review A, A23)."""
    require(container, ValidatedContainer, "container")
    return _default_now(tuple(r for r in container.records if type(r) in SWEEP_TYPES))


def dedup(container, now):
    """Group observations by (run_id, scope_id). The caller's order is never mutated, and the
    group order is canonical, so a permuted batch produces an equal result (Review A, A22)."""
    require(container, ValidatedContainer, "container")
    records = tuple(r for r in container.records if type(r) in SWEEP_TYPES)
    require(now, Epoch, "now")

    buckets = {}
    for rec in records:
        ident = observation_identity(rec)
        buckets.setdefault(ident, []).append(rec)
    order = sorted(buckets, key=lambda ident: (ident[0].text, ident[1].text))

    groups, usable, conflicts, retries, reasons = [], [], 0, 0, []
    if container.rejections:
        reasons.append(Reason.RECORD_UNREADABLE)
    for ident in order:
        members = canonical_order(tuple(buckets[ident]))
        run_id, scope = ident
        if len(members) == 1:
            groups.append(make_group(run_id, scope, members, Outcome.SINGLE, members[0]))
            usable.append(members[0])
            continue
        if len({m.equivalence() for m in members}) == 1:
            newest = canonical_representative(members)
            retries += 1
            groups.append(make_group(run_id, scope, members, Outcome.RETRY, newest))
            usable.append(newest)
        else:
            conflicts += 1
            if Reason.DEDUP_CONFLICT not in reasons:
                reasons.append(Reason.DEDUP_CONFLICT)
            groups.append(make_group(run_id, scope, members, Outcome.CONFLICT,
                                     Absence.KNOWN_ABSENT))
    return make_dedup_result(tuple(groups), tuple(usable), conflicts, retries, tuple(reasons),
                             len(container.rejections))
