"""Normalized branch facts used as a bridge toward a recursive pattern IR."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst

from .patterns import build_class_pattern, build_value_pattern
from .subject_path import SubjectPath


@dataclass(frozen=True)
class ValueFact:
    """A subject-path value check that can become a match value pattern."""

    path: SubjectPath
    value: cst.BaseExpression


@dataclass(frozen=True)
class ClassFact:
    """A subject-path isinstance check that can become a class pattern."""

    path: SubjectPath
    classes: tuple[cst.BaseExpression, ...]


BranchFact = ValueFact | ClassFact


@dataclass(frozen=True)
class PatternTree:
    """Intermediate pattern node that can render to a LibCST match pattern.

    This can either wrap already-built LibCST patterns for unmigrated recognizers
    or render simple fact-backed nodes directly.
    """

    pattern: cst.MatchPattern | None = None
    value_fact: ValueFact | None = None
    class_fact: ClassFact | None = None
    attribute_value_facts: tuple[ValueFact, ...] = ()

    def render(self) -> cst.MatchPattern:
        if self.value_fact is not None:
            if not self.value_fact.path.is_subject:
                raise ValueError("Value facts for derived paths need a parent pattern")
            return build_value_pattern(self.value_fact.value)
        if self.class_fact is not None:
            if not self.class_fact.path.is_subject:
                raise ValueError("Class facts for derived paths need a parent pattern")
            keyword_patterns = []
            for fact in self.attribute_value_facts:
                attr_name = fact.path.direct_attribute_name
                if attr_name is None:
                    raise ValueError(
                        "Only direct attribute value facts can render here"
                    )
                keyword_patterns.append((attr_name, build_value_pattern(fact.value)))
            return build_class_pattern(list(self.class_fact.classes), keyword_patterns)
        if self.pattern is None:
            raise ValueError("PatternTree has no renderable node")
        return self.pattern


@dataclass(frozen=True)
class BranchFacts:
    """Normalized facts for one branch condition."""

    condition: cst.BaseExpression
    subject: cst.BaseExpression
    facts: tuple[BranchFact, ...]
    pattern: PatternTree | None
    guard: cst.BaseExpression | None
