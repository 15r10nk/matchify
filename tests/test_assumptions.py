from functools import reduce
from operator import or_

from matchify.assumptions import (
    ALL_ASSUMPTION_FLAGS,
    ALL_RISKY_ASSUMPTIONS,
    Assumptions,
)


def test_from_names_enables_matching_flag_bits():
    assumptions = Assumptions.from_names(
        {"pure-subjects", "lookup-equality", "hashable-subjects"}
    )

    assert assumptions == (
        Assumptions.PURE_SUBJECTS
        | Assumptions.LOOKUP_EQUALITY
        | Assumptions.HASHABLE_SUBJECTS
    )
    assert assumptions.names == frozenset(
        {"pure-subjects", "lookup-equality", "hashable-subjects"}
    )
    assert Assumptions.PURE_SUBJECTS in assumptions
    assert Assumptions.LOOKUP_EQUALITY in assumptions
    assert Assumptions.HASHABLE_SUBJECTS in assumptions
    assert Assumptions.USE_OBJECT not in assumptions


def test_safe_and_risky_round_trip_through_names():
    assert Assumptions.safe() is Assumptions.NONE
    assert Assumptions.safe().names == frozenset()
    assert Assumptions.risky().names == ALL_RISKY_ASSUMPTIONS


def test_flag_enum_helpers_drive_name_conversion():
    assert list(Assumptions) == [
        Assumptions.PURE_SUBJECTS,
        Assumptions.USE_OBJECT,
        Assumptions.IDENTITY_EQUALITY,
        Assumptions.LIST_SEQUENCE_PATTERN,
        Assumptions.TUPLE_SEQUENCE_PATTERN,
        Assumptions.LOOKUP_EQUALITY,
        Assumptions.HASHABLE_SUBJECTS,
    ]
    assert Assumptions["PURE_SUBJECTS"] is Assumptions.PURE_SUBJECTS
    assert (
        Assumptions.from_assumption_name("pure-subjects") is Assumptions.PURE_SUBJECTS
    )
    assert ALL_ASSUMPTION_FLAGS == reduce(or_, Assumptions, Assumptions.NONE)
