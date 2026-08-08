"""Risky transformation assumptions."""

from collections.abc import Iterable
from dataclasses import dataclass

PURE_SUBJECTS = "pure-subjects"
USE_OBJECT = "use-object"
IDENTITY_EQUALITY = "identity-equality"
LIST_SEQUENCE_PATTERN = "list-sequence-pattern"
TUPLE_SEQUENCE_PATTERN = "tuple-sequence-pattern"
LOOKUP_EQUALITY = "lookup-equality"
HASHABLE_SUBJECTS = "hashable-subjects"

ALL_RISKY_ASSUMPTIONS = frozenset(
    {
        PURE_SUBJECTS,
        USE_OBJECT,
        IDENTITY_EQUALITY,
        LIST_SEQUENCE_PATTERN,
        TUPLE_SEQUENCE_PATTERN,
        LOOKUP_EQUALITY,
        HASHABLE_SUBJECTS,
    }
)
DEFAULT_ASSUMPTIONS = frozenset[str]()


@dataclass(frozen=True)
class AssumptionDiagnostic:
    """A skipped conversion that needs risky assumptions."""

    line: int
    column: int
    assumptions: frozenset[str]


@dataclass(frozen=True)
class Assumptions:
    """Enabled risky transformation assumptions."""

    names: frozenset[str] = DEFAULT_ASSUMPTIONS

    @classmethod
    def from_names(cls, names: Iterable[str] | None = None) -> "Assumptions":
        resolved = DEFAULT_ASSUMPTIONS if names is None else frozenset(names)
        unknown = resolved - ALL_RISKY_ASSUMPTIONS
        if unknown:
            names_list = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown risky assumption: {names_list}")
        return cls(resolved)

    @classmethod
    def risky(cls) -> "Assumptions":
        return cls(ALL_RISKY_ASSUMPTIONS)

    @classmethod
    def safe(cls) -> "Assumptions":
        return cls(frozenset())

    @property
    def assume_pure_subjects(self) -> bool:
        return PURE_SUBJECTS in self.names

    @property
    def use_object(self) -> bool:
        return USE_OBJECT in self.names

    @property
    def identity_equality(self) -> bool:
        return IDENTITY_EQUALITY in self.names

    @property
    def list_sequence_pattern(self) -> bool:
        return LIST_SEQUENCE_PATTERN in self.names

    @property
    def tuple_sequence_pattern(self) -> bool:
        return TUPLE_SEQUENCE_PATTERN in self.names

    @property
    def lookup_equality(self) -> bool:
        return LOOKUP_EQUALITY in self.names

    @property
    def hashable_subjects(self) -> bool:
        return HASHABLE_SUBJECTS in self.names


def parse_assumption_names(value: str) -> frozenset[str]:
    """Parse a comma-separated assumption list."""
    names = frozenset(name.strip() for name in value.split(",") if name.strip())
    Assumptions.from_names(names)
    return names
