"""Risky transformation assumptions."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Flag, auto
from functools import reduce
from operator import or_


class Assumptions(Flag):
    """Bit flags for risky transformation assumptions."""

    NONE = 0
    PURE_SUBJECTS = auto()
    USE_OBJECT = auto()
    IDENTITY_EQUALITY = auto()
    LIST_SEQUENCE_PATTERN = auto()
    TUPLE_SEQUENCE_PATTERN = auto()
    LOOKUP_EQUALITY = auto()
    HASHABLE_SUBJECTS = auto()

    @property
    def assumption_name(self) -> str:
        return self.name.lower().replace("_", "-")

    @classmethod
    def from_assumption_name(cls, name: str) -> "Assumptions":
        return cls[name.upper().replace("-", "_")]

    @classmethod
    def from_names(cls, names: Iterable[str] | None = None) -> "Assumptions":
        resolved = DEFAULT_ASSUMPTIONS if names is None else frozenset(names)
        unknown_names = []
        flags = cls.NONE
        for name in resolved:
            try:
                flags |= cls.from_assumption_name(name)
            except KeyError:
                unknown_names.append(name)
        if unknown_names:
            names_list = ", ".join(sorted(unknown_names))
            raise ValueError(f"Unknown risky assumption: {names_list}")
        return flags

    @classmethod
    def risky(cls) -> "Assumptions":
        return ALL_ASSUMPTION_FLAGS

    @classmethod
    def safe(cls) -> "Assumptions":
        return cls.NONE

    @property
    def names(self) -> frozenset[str]:
        return frozenset(flag.assumption_name for flag in self)


ALL_RISKY_ASSUMPTIONS = frozenset(flag.assumption_name for flag in Assumptions)
DEFAULT_ASSUMPTIONS = frozenset[str]()
ALL_ASSUMPTION_FLAGS = reduce(or_, Assumptions, Assumptions.NONE)


@dataclass(frozen=True)
class AssumptionDiagnostic:
    """A skipped conversion that needs risky assumptions."""

    line: int
    column: int
    assumptions: frozenset[str]


def parse_assumption_names(value: str) -> frozenset[str]:
    """Parse a comma-separated assumption list."""
    names = frozenset(name.strip() for name in value.split(",") if name.strip())
    Assumptions.from_names(names)
    return names
