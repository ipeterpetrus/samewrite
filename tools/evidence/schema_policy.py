"""Section 13 + B.9 - which machine-output change forces a schema bump, decided mechanically.

A schema here is a typed description, not a mapping of mappings: the thing that decides whether a
change is breaking should not itself be readable only by guessing at keys.
"""
import dataclasses
import enum
import typing

from .closed import Closed, ConstructionError


class FieldKind(enum.Enum):
    IDENTIFIER = "identifier"
    CLOSED_ENUM = "closed_enum"
    OPEN_SET = "open_set"
    INT = "int"
    STR = "str"
    BOOL = "bool"
    OBJECT = "object"
    ARRAY = "array"


@dataclasses.dataclass(frozen=True, init=False)
class FieldSpec(Closed):
    name: str
    kind: FieldKind
    required: bool
    semantics: int
    domain: typing.Tuple[str, ...]


@dataclasses.dataclass(frozen=True, init=False)
class OutputSchema(Closed):
    fields: typing.Tuple[FieldSpec, ...]

    def field(self, name):
        for f in self.fields:
            if f.name == name:
                return f
        return None

    @property
    def names(self):
        return tuple(f.name for f in self.fields)


@dataclasses.dataclass(frozen=True, init=False)
class Change(Closed):
    bump: bool
    reasons: typing.Tuple[str, ...]

    def __repr__(self):
        return "Change(bump=%s, %s)" % (self.bump, list(self.reasons))


def make_field_spec(name, kind, required, semantics, domain, field="field_spec"):
    from . import forms as f
    from .domains import Reason

    def need(ok, what, detail):
        if not ok:
            raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field + "." + what, detail)
    need(f.is_identifier(name), "name", "an identifier")
    from .domains import member_of
    kind = member_of(FieldKind, kind, field + ".kind", Reason.RECORD_SHAPE_INVALID)
    need(f.is_bool(required), "required", "exactly true or false")
    need(f.is_nat(semantics), "semantics", "a non-negative int")
    need(type(domain) is tuple and all(f.is_str(d) for d in domain), "domain",
         "a tuple of strings")
    return FieldSpec._seal(name=name, kind=kind, required=required, semantics=semantics,
                           domain=domain)


def make_output_schema(fields, field="schema"):
    from .domains import Reason
    if type(fields) is not tuple or any(type(s) is not FieldSpec for s in fields):
        raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field, "a tuple of field specs")
    names = [s.name for s in fields]
    if len(set(names)) != len(names):
        raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field, "one spec per field name")
    return OutputSchema._seal(fields=tuple(sorted(fields, key=lambda s: s.name)))


def make_change(bump, reasons, field="change"):
    from . import forms as f
    from .domains import Reason
    if not f.is_bool(bump):
        raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field + ".bump", "a boolean")
    if type(reasons) is not tuple or any(not f.is_str(r) for r in reasons):
        raise ConstructionError(Reason.RECORD_SHAPE_INVALID, field + ".reasons",
                                "a tuple of strings")
    return Change._seal(bump=bump, reasons=reasons)


def classify_change(old, new):
    """Compare two typed schemas and say whether the machine output may keep its version."""
    from .domains import DomainError
    if type(old) is not OutputSchema or type(new) is not OutputSchema:
        raise DomainError("classify_change takes two OutputSchema values")
    reasons = []

    def add(code, field):
        entry = "%s:%s" % (code, field)
        if entry not in reasons:
            reasons.append(entry)
        if code not in reasons:
            reasons.append(code)

    for spec in sorted(old.fields, key=lambda f: f.name):
        other = new.field(spec.name)
        if other is None:
            add("removed_field", spec.name)
            continue
        if spec.kind is not other.kind:
            add("type_change", spec.name)
            continue
        if spec.semantics != other.semantics:
            add("semantic_change", spec.name)
        if spec.required and not other.required:
            add("guarantee_removed", spec.name)
        if spec.kind in (FieldKind.CLOSED_ENUM, FieldKind.OPEN_SET):
            before, after = set(spec.domain), set(other.domain)
            if before - after:
                add("narrowed_domain", spec.name)
            elif after - before and spec.kind is FieldKind.CLOSED_ENUM:
                add("widened_closed_domain", spec.name)
    for spec in sorted(new.fields, key=lambda f: f.name):
        if old.field(spec.name) is None and spec.required:
            add("added_required_field", spec.name)
    return make_change(bool(reasons), tuple(reasons))
