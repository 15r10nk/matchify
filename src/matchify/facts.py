"""Normalized branch facts used as a bridge toward a recursive pattern IR."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst

from .patterns import build_class_pattern, build_or_pattern, build_value_pattern
from .sequence_patterns import (
    LiteralElementPattern,
    RawElementPattern,
    SequenceElementPattern,
    WildcardElementPattern,
    build_sequence_match_list,
    validate_wildcard_constraint,
)
from .subject_path import AttributePathPart, SubjectPath, SubscriptPathPart


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


@dataclass(frozen=True)
class SequenceFact:
    """A subject sequence length check that can become a sequence pattern."""

    path: SubjectPath
    length: int
    use_star: bool = False


@dataclass(frozen=True)
class CaptureFact:
    """A body assignment that can become a match capture pattern."""

    name: str
    path: SubjectPath
    index: int


@dataclass(frozen=True)
class OrFact:
    """Multiple alternative facts for the same subject path."""

    path: SubjectPath
    alternatives: tuple[ValueFact | ClassFact | PatternTree, ...]


PathFact = ValueFact | ClassFact | SequenceFact | OrFact
BranchFact = PathFact


@dataclass(frozen=True)
class PatternTree:
    """Intermediate pattern node that can render to a LibCST match pattern."""

    value_fact: ValueFact | None = None
    class_fact: ClassFact | None = None
    sequence_fact: SequenceFact | None = None
    attribute_value_facts: tuple[ValueFact, ...] = ()
    attribute_class_facts: tuple[ClassFact, ...] = ()
    attribute_sequence_facts: tuple[SequenceFact, ...] = ()
    attribute_or_facts: tuple[OrFact, ...] = ()
    attribute_capture_facts: tuple[CaptureFact, ...] = ()
    sequence_value_facts: tuple[ValueFact, ...] = ()
    sequence_class_facts: tuple[ClassFact, ...] = ()
    sequence_sequence_facts: tuple[SequenceFact, ...] = ()
    sequence_or_facts: tuple[OrFact, ...] = ()
    sequence_capture_facts: tuple[CaptureFact, ...] = ()
    or_patterns: tuple[PatternTree, ...] = ()

    @classmethod
    def from_value_fact(cls, fact: ValueFact) -> PatternTree:
        return cls(value_fact=fact)

    @classmethod
    def from_class_fact(
        cls,
        fact: ClassFact,
        *,
        value_facts: tuple[ValueFact, ...] = (),
        class_facts: tuple[ClassFact, ...] = (),
        sequence_facts: tuple[SequenceFact, ...] = (),
        or_facts: tuple[OrFact, ...] = (),
        capture_facts: tuple[CaptureFact, ...] = (),
    ) -> PatternTree:
        return cls(
            class_fact=fact,
            attribute_value_facts=value_facts,
            attribute_class_facts=class_facts,
            attribute_sequence_facts=sequence_facts,
            attribute_or_facts=or_facts,
            attribute_capture_facts=capture_facts,
        )

    @classmethod
    def from_sequence_fact(
        cls,
        fact: SequenceFact,
        *,
        value_facts: tuple[ValueFact, ...] = (),
        class_facts: tuple[ClassFact, ...] = (),
        sequence_facts: tuple[SequenceFact, ...] = (),
        or_facts: tuple[OrFact, ...] = (),
        capture_facts: tuple[CaptureFact, ...] = (),
    ) -> PatternTree:
        return cls(
            sequence_fact=fact,
            sequence_value_facts=value_facts,
            sequence_class_facts=class_facts,
            sequence_sequence_facts=sequence_facts,
            sequence_or_facts=or_facts,
            sequence_capture_facts=capture_facts,
        )

    @classmethod
    def from_or_patterns(cls, patterns: tuple[PatternTree, ...]) -> PatternTree:
        return cls(or_patterns=patterns)

    def with_captures(self, capture_facts: tuple[CaptureFact, ...]) -> PatternTree:
        if not capture_facts:
            return self
        if self.or_patterns:
            return PatternTree(
                or_patterns=tuple(
                    pattern.with_captures(capture_facts) for pattern in self.or_patterns
                )
            )
        if self.class_fact is not None:
            return PatternTree(
                class_fact=self.class_fact,
                attribute_value_facts=self.attribute_value_facts,
                attribute_class_facts=self.attribute_class_facts,
                attribute_sequence_facts=self.attribute_sequence_facts,
                attribute_or_facts=self.attribute_or_facts,
                attribute_capture_facts=(
                    *self.attribute_capture_facts,
                    *capture_facts,
                ),
            )
        if self.sequence_fact is not None:
            return PatternTree(
                sequence_fact=self.sequence_fact,
                sequence_value_facts=self.sequence_value_facts,
                sequence_class_facts=self.sequence_class_facts,
                sequence_sequence_facts=self.sequence_sequence_facts,
                sequence_or_facts=self.sequence_or_facts,
                sequence_capture_facts=(
                    *self.sequence_capture_facts,
                    *capture_facts,
                ),
            )
        return self

    def render(self) -> cst.MatchPattern:
        if self.or_patterns:
            return build_or_pattern(
                [
                    bracket_or_sequence_pattern(pattern.render())
                    for pattern in self.or_patterns
                ]
            )
        if self.value_fact is not None:
            if not self.value_fact.path.is_subject:
                raise ValueError("Value facts for derived paths need a parent pattern")
            return build_value_pattern(self.value_fact.value)
        if self.class_fact is not None:
            if not self.class_fact.path.is_subject:
                raise ValueError("Class facts for derived paths need a parent pattern")
            return render_class_fact(
                self.class_fact,
                self.attribute_value_facts,
                self.attribute_class_facts,
                self.attribute_sequence_facts,
                self.attribute_or_facts,
                self.attribute_capture_facts,
            )
        if self.sequence_fact is not None:
            if not self.sequence_fact.path.is_subject:
                raise ValueError(
                    "Sequence facts for derived paths need a parent pattern"
                )
            return render_sequence_fact(
                self.sequence_fact,
                self.sequence_value_facts,
                self.sequence_class_facts,
                self.sequence_sequence_facts,
                self.sequence_or_facts,
                self.sequence_capture_facts,
            )
        raise ValueError("PatternTree has no renderable node")


@dataclass(frozen=True)
class BranchFacts:
    """Normalized facts for one branch condition."""

    condition: cst.BaseExpression
    subject: cst.BaseExpression
    facts: tuple[BranchFact, ...]
    pattern: PatternTree | None
    guard: cst.BaseExpression | None

    def with_pattern(self, pattern: PatternTree | None) -> BranchFacts:
        return BranchFacts(
            condition=self.condition,
            subject=self.subject,
            facts=self.facts,
            pattern=pattern,
            guard=self.guard,
        )

    @classmethod
    def from_value_fact(
        cls,
        condition: cst.BaseExpression,
        subject: cst.BaseExpression,
        fact: ValueFact,
        *,
        guard: cst.BaseExpression | None = None,
    ) -> BranchFacts:
        return cls(
            condition=condition,
            subject=subject,
            facts=(fact,),
            pattern=PatternTree.from_value_fact(fact),
            guard=guard,
        )

    @classmethod
    def from_class_fact(
        cls,
        condition: cst.BaseExpression,
        subject: cst.BaseExpression,
        fact: ClassFact,
        *,
        value_facts: tuple[ValueFact, ...] = (),
        class_facts: tuple[ClassFact, ...] = (),
        sequence_facts: tuple[SequenceFact, ...] = (),
        or_facts: tuple[OrFact, ...] = (),
        capture_facts: tuple[CaptureFact, ...] = (),
        guard: cst.BaseExpression | None = None,
    ) -> BranchFacts:
        return cls(
            condition=condition,
            subject=subject,
            facts=(fact, *sequence_facts, *or_facts, *value_facts, *class_facts),
            pattern=PatternTree.from_class_fact(
                fact,
                value_facts=value_facts,
                class_facts=class_facts,
                sequence_facts=sequence_facts,
                or_facts=or_facts,
                capture_facts=capture_facts,
            ),
            guard=guard,
        )

    @classmethod
    def from_sequence_fact(
        cls,
        condition: cst.BaseExpression,
        subject: cst.BaseExpression,
        fact: SequenceFact,
        *,
        value_facts: tuple[ValueFact, ...] = (),
        class_facts: tuple[ClassFact, ...] = (),
        sequence_facts: tuple[SequenceFact, ...] = (),
        or_facts: tuple[OrFact, ...] = (),
        capture_facts: tuple[CaptureFact, ...] = (),
        guard: cst.BaseExpression | None = None,
    ) -> BranchFacts:
        return cls(
            condition=condition,
            subject=subject,
            facts=(fact, *or_facts, *sequence_facts, *value_facts, *class_facts),
            pattern=PatternTree.from_sequence_fact(
                fact,
                value_facts=value_facts,
                class_facts=class_facts,
                sequence_facts=sequence_facts,
                or_facts=or_facts,
                capture_facts=capture_facts,
            ),
            guard=guard,
        )

    @classmethod
    def from_or_patterns(
        cls,
        condition: cst.BaseExpression,
        subject: cst.BaseExpression,
        facts: tuple[BranchFact, ...],
        patterns: tuple[PatternTree, ...],
        *,
        guard: cst.BaseExpression | None = None,
    ) -> BranchFacts:
        return cls(
            condition=condition,
            subject=subject,
            facts=facts,
            pattern=PatternTree.from_or_patterns(patterns),
            guard=guard,
        )


def render_class_fact(
    class_fact: ClassFact,
    value_facts: tuple[ValueFact, ...],
    class_facts: tuple[ClassFact, ...],
    sequence_facts: tuple[SequenceFact, ...],
    or_facts: tuple[OrFact, ...],
    capture_facts: tuple[CaptureFact, ...] = (),
) -> cst.MatchPattern:
    keyword_patterns: list[tuple[str, cst.MatchPattern]] = []
    seen_attributes: set[str] = set()
    direct_pattern_attributes = {
        attr_name
        for fact in (*class_facts, *sequence_facts, *or_facts)
        for attr_name in (direct_attribute_name(fact.path),)
        if attr_name is not None
    }

    for fact in or_facts:
        attr_name = direct_attribute_name(fact.path)
        if attr_name is None:
            continue
        if attr_name in seen_attributes:
            raise ValueError("Duplicate attribute facts cannot render here")
        seen_attributes.add(attr_name)
        keyword_patterns.append(
            (
                attr_name,
                render_or_fact(fact, strip_capture_prefix(attr_name, capture_facts)),
            )
        )

    for fact in sequence_facts:
        attr_name = direct_attribute_name(fact.path)
        if attr_name is None:
            continue
        if attr_name in seen_attributes:
            raise ValueError("Duplicate attribute facts cannot render here")
        seen_attributes.add(attr_name)
        keyword_patterns.append(
            (
                attr_name,
                bracket_sequence_pattern(
                    render_sequence_fact(
                        SequenceFact(SubjectPath(()), fact.length, fact.use_star),
                        strip_fact_prefix(attr_name, value_facts),
                        strip_fact_prefix(attr_name, class_facts),
                        strip_fact_prefix(attr_name, sequence_facts),
                        strip_fact_prefix(attr_name, or_facts),
                        strip_capture_prefix(attr_name, capture_facts),
                    )
                ),
            )
        )

    for fact in value_facts:
        names = fact.path.attribute_names
        if (
            names is None
            and first_attribute_name(fact.path) in direct_pattern_attributes
        ):
            continue
        if names is None or not names:
            raise ValueError("Value facts for class patterns need attribute paths")
        if len(names) > 1:
            continue
        attr_name = names[0]
        if attr_name in seen_attributes or has_nested_fact(
            attr_name, value_facts, class_facts, sequence_facts, or_facts
        ):
            raise ValueError("Duplicate attribute facts cannot render here")
        seen_attributes.add(attr_name)
        keyword_patterns.append((attr_name, build_value_pattern(fact.value)))

    for fact in class_facts:
        names = fact.path.attribute_names
        if (
            names is None
            and first_attribute_name(fact.path) in direct_pattern_attributes
        ):
            continue
        if names is None or not names:
            raise ValueError("Class facts for class patterns need attribute paths")
        if len(names) > 1:
            continue
        attr_name = names[0]
        if attr_name in seen_attributes:
            raise ValueError("Duplicate attribute facts cannot render here")
        seen_attributes.add(attr_name)
        keyword_patterns.append(
            (
                attr_name,
                render_class_fact(
                    ClassFact(SubjectPath(()), fact.classes),
                    strip_fact_prefix(attr_name, value_facts),
                    strip_fact_prefix(attr_name, class_facts),
                    strip_fact_prefix(attr_name, sequence_facts),
                    strip_fact_prefix(attr_name, or_facts),
                    strip_capture_prefix(attr_name, capture_facts),
                ),
            )
        )

    nested_pattern_attributes = {
        names[0]
        for fact in (*class_facts, *sequence_facts, *or_facts)
        for names in (fact.path.attribute_names,)
        if names is not None and len(names) == 1
    }
    unused_value_facts = [
        fact
        for fact in value_facts
        if (names := fact.path.attribute_names) is not None
        and len(names) > 1
        and names[0] not in nested_pattern_attributes
    ]
    unused_class_facts = [
        fact
        for fact in class_facts
        if (names := fact.path.attribute_names) is not None
        and len(names) > 1
        and names[0] not in nested_pattern_attributes
    ]
    unused_sequence_facts = [
        fact
        for fact in sequence_facts
        if (names := fact.path.attribute_names) is not None
        and len(names) > 1
        and names[0] not in nested_pattern_attributes
    ]
    unused_or_facts = [
        fact
        for fact in or_facts
        if (names := fact.path.attribute_names) is not None
        and len(names) > 1
        and names[0] not in nested_pattern_attributes
    ]
    if (
        unused_value_facts
        or unused_class_facts
        or unused_sequence_facts
        or unused_or_facts
    ):
        raise ValueError("Nested facts need an enclosing class fact")

    return build_class_pattern(list(class_fact.classes), keyword_patterns)


def has_nested_fact(
    attr_name: str,
    value_facts: tuple[ValueFact, ...],
    class_facts: tuple[ClassFact, ...],
    sequence_facts: tuple[SequenceFact, ...],
    or_facts: tuple[OrFact, ...],
) -> bool:
    return any(
        names is not None and len(names) > 1 and names[0] == attr_name
        for fact in (*value_facts, *class_facts, *sequence_facts, *or_facts)
        for names in (fact.path.attribute_names,)
    )


def strip_fact_prefix(
    attr_name: str,
    facts: tuple[PathFact, ...],
) -> tuple[PathFact, ...]:
    stripped: list[PathFact] = []
    for fact in facts:
        if len(fact.path.parts) <= 1 or fact.path.first_part != AttributePathPart(
            attr_name
        ):
            continue
        path = fact.path.tail()
        stripped.append(replace_fact_path(fact, path))
    return tuple(stripped)


def strip_capture_prefix(
    attr_name: str,
    facts: tuple[CaptureFact, ...],
) -> tuple[CaptureFact, ...]:
    stripped: list[CaptureFact] = []
    for fact in facts:
        if fact.path.first_part != AttributePathPart(attr_name):
            continue
        stripped.append(CaptureFact(fact.name, fact.path.tail(), fact.index))
    return tuple(stripped)


def direct_attribute_name(path: SubjectPath) -> str | None:
    if len(path.parts) != 1 or not isinstance(path.first_part, AttributePathPart):
        return None
    return path.first_part.name


def first_attribute_name(path: SubjectPath) -> str | None:
    if not isinstance(path.first_part, AttributePathPart):
        return None
    return path.first_part.name


def render_sequence_fact(
    sequence_fact: SequenceFact,
    value_facts: tuple[ValueFact, ...],
    class_facts: tuple[ClassFact, ...],
    sequence_facts: tuple[SequenceFact, ...] = (),
    or_facts: tuple[OrFact, ...] = (),
    capture_facts: tuple[CaptureFact, ...] = (),
) -> cst.MatchPattern:
    elements: dict[int, SequenceElementPattern] = {}
    direct_sequence_indices = {
        index
        for fact in sequence_facts
        for index in (sequence_element_index(fact.path),)
        if index is not None
    }
    direct_class_indices = {
        index
        for fact in class_facts
        for index in (sequence_element_index(fact.path),)
        if index is not None
    }

    for fact in value_facts:
        index = sequence_element_index(fact.path)
        if index is None and first_sequence_index(fact.path) in (
            direct_sequence_indices | direct_class_indices
        ):
            continue
        if index is None or index in elements:
            raise ValueError("Invalid sequence value fact")
        elements[index] = LiteralElementPattern(fact.value)

    for fact in class_facts:
        index = sequence_element_index(fact.path)
        if index is None and first_sequence_index(fact.path) in (
            direct_sequence_indices | direct_class_indices
        ):
            continue
        if index is None or index in elements:
            raise ValueError("Invalid sequence class fact")
        elements[index] = RawElementPattern(
            render_class_fact(
                ClassFact(SubjectPath(()), fact.classes),
                strip_sequence_fact_prefix(index, value_facts),
                strip_sequence_fact_prefix(index, class_facts),
                strip_sequence_fact_prefix(index, sequence_facts),
                strip_sequence_fact_prefix(index, or_facts),
                strip_sequence_capture_prefix(index, capture_facts),
            )
        )

    for fact in sequence_facts:
        index = sequence_element_index(fact.path)
        if index is None and first_sequence_index(fact.path) in (
            direct_sequence_indices | direct_class_indices
        ):
            continue
        if index is None or index in elements:
            raise ValueError("Invalid nested sequence fact")
        elements[index] = RawElementPattern(
            bracket_sequence_pattern(
                render_sequence_fact(
                    SequenceFact(SubjectPath(()), fact.length, fact.use_star),
                    strip_sequence_fact_prefix(index, value_facts),
                    strip_sequence_fact_prefix(index, class_facts),
                    strip_sequence_fact_prefix(index, sequence_facts),
                    strip_sequence_fact_prefix(index, or_facts),
                    strip_sequence_capture_prefix(index, capture_facts),
                )
            )
        )

    for fact in or_facts:
        index = sequence_element_index(fact.path)
        if index is None and first_sequence_index(fact.path) in (
            direct_sequence_indices | direct_class_indices
        ):
            continue
        if index is None or index in elements:
            raise ValueError("Invalid sequence OR fact")
        elements[index] = RawElementPattern(
            render_or_fact(fact, strip_sequence_capture_prefix(index, capture_facts))
        )

    for fact in capture_facts:
        index = capture_element_index(fact)
        if index is None:
            continue
        elements[index] = RawElementPattern(
            cst.MatchAs(pattern=None, name=cst.Name(fact.name))
        )

    required_len = sequence_fact.length
    if sequence_fact.use_star and elements:
        required_len = max(elements) + 1

    if not sequence_fact.use_star and elements and max(elements) >= required_len:
        raise ValueError("Sequence element facts exceed the checked length")
    if not sequence_fact.use_star and not validate_wildcard_constraint(
        elements, required_len
    ):
        raise ValueError("Sequence fact would produce too many wildcards")

    pattern_infos = [
        elements.get(index, WildcardElementPattern()) for index in range(required_len)
    ]
    return build_sequence_match_list(pattern_infos, use_star=sequence_fact.use_star)


def bracket_or_sequence_pattern(pattern: cst.MatchPattern) -> cst.MatchPattern:
    if isinstance(pattern, cst.MatchList):
        return bracket_sequence_pattern(pattern)
    return pattern


def bracket_sequence_pattern(pattern: cst.MatchList) -> cst.MatchList:
    patterns = pattern.patterns
    if len(patterns) == 1:
        only_element = patterns[0]
        patterns = [cst.MatchSequenceElement(value=only_element.value)]
    return pattern.with_changes(
        patterns=patterns,
        lbracket=cst.LeftSquareBracket(),
        rbracket=cst.RightSquareBracket(),
    )


def sequence_element_index(path: SubjectPath) -> int | None:
    if len(path.parts) != 1 or not isinstance(path.first_part, SubscriptPathPart):
        return None
    return path.first_part.index


def first_sequence_index(path: SubjectPath) -> int | None:
    if not isinstance(path.first_part, SubscriptPathPart):
        return None
    return path.first_part.index


def capture_element_index(fact: CaptureFact) -> int | None:
    if fact.path.is_subject:
        return fact.index
    return None


def strip_sequence_fact_prefix(
    index: int,
    facts: tuple[PathFact, ...],
) -> tuple[PathFact, ...]:
    stripped: list[PathFact] = []
    prefix = SubscriptPathPart(index)
    for fact in facts:
        if len(fact.path.parts) <= 1 or fact.path.first_part != prefix:
            continue
        path = fact.path.tail()
        stripped.append(replace_fact_path(fact, path))
    return tuple(stripped)


def strip_sequence_capture_prefix(
    index: int,
    facts: tuple[CaptureFact, ...],
) -> tuple[CaptureFact, ...]:
    stripped: list[CaptureFact] = []
    prefix = SubscriptPathPart(index)
    for fact in facts:
        if fact.path.first_part != prefix:
            continue
        stripped.append(CaptureFact(fact.name, fact.path.tail(), fact.index))
    return tuple(stripped)


def render_or_fact(
    fact: OrFact, capture_facts: tuple[CaptureFact, ...] = ()
) -> cst.MatchPattern:
    patterns = []
    for alternative in fact.alternatives:
        if isinstance(alternative, ValueFact):
            patterns.append(build_value_pattern(alternative.value))
        elif isinstance(alternative, ClassFact):
            patterns.append(build_class_pattern(list(alternative.classes)))
        else:
            patterns.append(
                bracket_or_sequence_pattern(
                    alternative.with_captures(capture_facts).render()
                )
            )
    return build_or_pattern(patterns)


def strip_or_alternative_prefix(
    fact: OrFact, path: SubjectPath
) -> tuple[ValueFact | ClassFact | PatternTree, ...]:
    alternatives: list[ValueFact | ClassFact | PatternTree] = []
    for alternative in fact.alternatives:
        if isinstance(alternative, ValueFact):
            alternatives.append(ValueFact(path, alternative.value))
        elif isinstance(alternative, ClassFact):
            alternatives.append(ClassFact(path, alternative.classes))
        else:
            alternatives.append(alternative)
    return tuple(alternatives)


def replace_fact_path(fact: PathFact, path: SubjectPath) -> PathFact:
    if isinstance(fact, ValueFact):
        return ValueFact(path, fact.value)
    if isinstance(fact, ClassFact):
        return ClassFact(path, fact.classes)
    if isinstance(fact, SequenceFact):
        return SequenceFact(path, fact.length, fact.use_star)
    return OrFact(path, strip_or_alternative_prefix(fact, path))
