"""Closed semantic types, and the one thing that is allowed to allocate them.

Phase 1R had two validation authorities for every type: the wire decoder, which established
domains, membership, cross-field relations and registry facts, and a generic `mint()` reading a
parallel rule table, which established field types only. Review B proved they diverge -- a
`SweepRecord` whose envelope said `history_quarantine`, a `DiscoveryConfig` with an unsupported
schema, a `FindingId` outside the registry. A test that compares two validators is weaker than
having one.

Phase 1S removes the second authority. There is no generic constructor and no rule table. For
each semantic type there is exactly ONE function that establishes every invariant of that type,
and both the wire decoder and internal derivation call it.

What remains here is allocation, not validation:

    Closed          a semantic type: not subclassable, no public constructor
    Closed._seal    the allocation primitive, used ONLY inside a type's own constructor

`_seal` decides nothing. It cannot: it has no schema, no rules, no domain knowledge. The static
test `tests/test_single_authority.py` keeps its callers inside the constructor functions.

THIS IS TYPE AND PROJECT INTEGRITY, NOT A PYTHON SANDBOX OR SECURITY BOUNDARY. A caller with
arbitrary Python can reach `object.__new__`, rebind a module attribute or mutate `__dict__`. The
guarantee is about SameWrite's supported code paths and API, and nothing wider.
"""


import sys


class ConstructionError(ValueError):
    """A semantic type was asked to exist in a state its constructor forbids."""

    def __init__(self, reason, field, detail=""):
        self.reason = reason
        self.field = field
        self.detail = detail
        super(ConstructionError, self).__init__(
            "%s: %s%s" % (getattr(reason, "value", reason), field,
                          (" -- " + detail) if detail else ""))


class Closed(object):
    """Base of every validated semantic type.

    Not subclassable beyond the semantic types themselves: Review B's B1 built a subclass with its
    own `__init__`, put "not-a-digest" in it, and `isinstance(x, Digest)` still said yes. A closed
    nominal type has no subclasses at all, so there is nothing for `isinstance` to be wrong about.
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__bases__ != (Closed,):
            raise ConstructionError("closed_type", cls.__name__,
                                    "a closed semantic type may not be subclassed")

    def __init__(self, *args, **kwargs):
        raise ConstructionError("closed_type", type(self).__name__,
                                "built by its own constructor, never called directly")

    @classmethod
    def _seal(cls, **fields):
        """Allocate. Validation happened in the caller, which is the type's one constructor.

        The static test confines the callers of this method to the constructor functions. This
        runtime check is the same rule enforced a second way, because a static whitelist is not a
        capability boundary: a caller OUTSIDE the evidence package cannot allocate at all. It is
        CPython-specific and it is not a sandbox -- `object.__new__` is still `object.__new__` --
        but it removes `Type._seal(...)` from the supported API surface.
        """
        caller = ""
        getframe = getattr(sys, "_getframe", None)
        if getframe is not None:
            caller = getframe(1).f_globals.get("__name__", "")
        if caller and not caller.startswith("evidence."):
            raise ConstructionError("closed_type", cls.__name__,
                                    "allocated from %s: only the type's own constructor may"
                                    % caller)
        obj = object.__new__(cls)
        for name, value in fields.items():
            object.__setattr__(obj, name, value)
        return obj
