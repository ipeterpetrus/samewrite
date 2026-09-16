"""Absence is evidence, so it is never spelled `None`.

The final Phase 1 review produced two findings whose whole content was that one `None` carried
three different meanings. A world that has no ledger, a world whose ledger could not be read, and
a ledger that is present all reach the classifier as the same value, so the classifier answered
the same way to three different situations.

Three states, named:
    Absence.KNOWN_ABSENT   the fact was established: there is nothing here
    Absence.UNVERIFIED     the fact could not be established
    the typed value itself  it is here, and it is valid
"""
import enum


class Absence(enum.Enum):
    KNOWN_ABSENT = "known_absent"
    UNVERIFIED = "unverified"

    def __repr__(self):
        return "Absence.%s" % self.name


KNOWN_ABSENT = Absence.KNOWN_ABSENT
UNVERIFIED = Absence.UNVERIFIED


def is_present(value):
    """True only for a real value. An Absence is not a value, and None is not an Absence."""
    return not isinstance(value, Absence)


def presence_of(value):
    """The three-way tag, for reason codes and reporting."""
    if isinstance(value, Absence):
        return value
    return "present"
