"""Normalized branch facts used as a bridge toward a recursive pattern IR."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst

from .patterns import (
    build_class_pattern,
    build_or_pattern,
    build_value_pattern,
    build_wildcard_pattern,
)
from .subject_path import (
    AccessPath,
    AttributePathPart,
    SubscriptPathPart,
)


@dataclass(frozen=True)
class ValueFact:
    """A subject-path value check that can become a match value pattern."""

    path: AccessPath
    value: cst.BaseExpression


@dataclass(frozen=True)
class ClassFact:
    """A subject-path isinstance check that can become a class pattern."""

    path: AccessPath
    classes: tuple[cst.BaseExpression, ...]


@dataclass(frozen=True)
class SequenceFact:
    """A subject sequence length check that can become a sequence pattern."""

    path: AccessPath
    length: int
    use_star: bool = False


@dataclass(frozen=True)
class CaptureFact:
    """A body assignment that can become a match capture pattern."""

    name: str
    path: AccessPath
    index: int


@dataclass(frozen=True)
class OrFact:
    """Multiple alternative facts for the same subject path."""

    path: AccessPath
    alternatives: tuple[ValueFact | ClassFact | tuple[PathFact, ...], ...]


PathFact = ValueFact | ClassFact | SequenceFact | OrFact


@dataclass(frozen=True)
class WildcardNode:
    """Wildcard placeholder used when a path creates an intermediate child."""


@dataclass(frozen=True)
class ValueNode:
    """A literal or singleton value pattern."""

    value: cst.BaseExpression

    def render(self) -> cst.MatchPattern:
        return build_value_pattern(self.value)


@dataclass(frozen=True)
class CaptureNode:
    """A capture pattern that binds one sequence element."""

    name: str

    def render(self) -> cst.MatchPattern:
        return cst.MatchAs(pattern=None, name=cst.Name(self.name))


@dataclass(frozen=True)
class ClassNode:
    """A class pattern with recursively nested attribute children."""

    classes: tuple[cst.BaseExpression, ...]
    attributes: tuple[tuple[str, PatternNode], ...] = ()

    def render(self) -> cst.MatchPattern:
        return build_class_pattern(
            self.classes,
            [(name, render_child_node(node)) for name, node in self.attributes],
        )


@dataclass(frozen=True)
class SequenceNode:
    """A sequence pattern with recursively nested element children."""

    length: int
    use_star: bool = False
    elements: tuple[tuple[int, PatternNode], ...] = ()

    def render(self) -> cst.MatchPattern:
        elements = dict(self.elements)
        max_element_index = max(elements) if elements else None
        required_len = self.length
        if self.use_star and max_element_index is not None:
            required_len = max_element_index + 1

        if not self.use_star:
            if max_element_index is not None and max_element_index >= required_len:
                raise ValueError("Sequence element facts exceed the checked length")
            consecutive_wildcards = 0
            for index in range(required_len):
                if index in elements:
                    consecutive_wildcards = 0
                    continue
                consecutive_wildcards += 1
                if consecutive_wildcards >= 3:
                    break
            if consecutive_wildcards >= 3:
                raise ValueError("Sequence fact would produce too many wildcards")

        pattern_infos: list[cst.MatchPattern | None] = [
            (render_child_node(elements[index]) if index in elements else None)
            for index in range(required_len)
        ]
        return build_sequence_match_list(pattern_infos, use_star=self.use_star)


@dataclass(frozen=True)
class OrNode:
    """An OR pattern with recursive alternatives."""

    alternatives: tuple[PatternNode, ...]

    def render(self) -> cst.MatchPattern:
        patterns = []
        for node in self.alternatives:
            pattern = node.render()
            if isinstance(pattern, cst.MatchList):
                pattern = bracket_sequence_pattern(pattern)
            patterns.append(pattern)
        return build_or_pattern(patterns)


PatternNode = WildcardNode | ValueNode | CaptureNode | ClassNode | SequenceNode | OrNode


def build_sequence_match_list(
    pattern_infos: list[cst.MatchPattern | None],
    use_star: bool,
) -> cst.MatchList:
    elements = [
        cst.MatchSequenceElement(
            value=(build_wildcard_pattern() if pattern_info is None else pattern_info),
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
        )
        for pattern_info in pattern_infos
    ]

    if use_star:
        elements.append(
            cst.MatchSequenceElement(value=cst.MatchStar(name=cst.Name("_")))
        )
        return cst.MatchList(patterns=elements, lbracket=None, rbracket=None)

    if len(elements) > 1:
        elements[-1] = cst.MatchSequenceElement(value=elements[-1].value)
    elif elements:  # pragma: no branch
        elements[-1] = cst.MatchSequenceElement(
            value=elements[-1].value,
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace("")),
        )
    return cst.MatchList(patterns=elements, lbracket=None, rbracket=None)


@dataclass(frozen=True)
class PatternTree:
    """Small wrapper around the explicit recursive pattern-node IR."""

    node: PatternNode

    @classmethod
    def from_facts(
        cls,
        facts: tuple[PathFact, ...],
    ) -> PatternTree:
        # Public normalization only builds PatternTree after at least one fact.
        if not facts:  # pragma: no cover
            raise ValueError("PatternTree needs at least one fact")

        # The builder orders facts so the first one always anchors the subject.
        first = facts[0]
        if not first.path.is_subject:  # pragma: no cover
            raise ValueError("First pattern fact must describe the subject")

        root = node_from_fact(first)
        for fact in facts[1:]:
            root = insert_node(root, fact.path, node_from_fact(fact))

        return cls(root)

    def with_capture(self, fact: CaptureFact) -> PatternTree | None:
        node = insert_capture_node(
            self.node,
            AccessPath(
                fact.path.root,
                (*fact.path.parts, SubscriptPathPart(fact.index)),
            ),
            CaptureNode(fact.name),
        )
        return None if node is None else PatternTree(node)

    def render(self) -> cst.MatchPattern:
        return self.node.render()


@dataclass(frozen=True)
class BranchFacts:
    """Normalized facts for one branch condition."""

    pattern: PatternTree | None
    guard: cst.BaseExpression | None


def node_from_fact(fact: PathFact) -> PatternNode:
    if isinstance(fact, ValueFact):
        return ValueNode(fact.value)
    if isinstance(fact, ClassFact):
        return ClassNode(fact.classes)
    if isinstance(fact, SequenceFact):
        return SequenceNode(fact.length, fact.use_star)
    return OrNode(
        tuple(
            node_from_or_alternative(alternative) for alternative in fact.alternatives
        )
    )


def node_from_or_alternative(
    alternative: ValueFact | ClassFact | tuple[PathFact, ...],
) -> PatternNode:
    if isinstance(alternative, ValueFact):
        return ValueNode(alternative.value)
    if isinstance(alternative, ClassFact):
        return ClassNode(alternative.classes)
    return PatternTree.from_facts(alternative).node


def insert_node(root: PatternNode, path: AccessPath, node: PatternNode) -> PatternNode:
    if isinstance(root, OrNode):
        if path.is_subject:
            raise ValueError("Conflicting facts for the same subject path")
        return OrNode(
            tuple(
                insert_node(alternative, path, node)
                for alternative in root.alternatives
            )
        )

    if path.is_subject:
        if isinstance(root, WildcardNode):
            return node
        raise ValueError("Conflicting facts for the same subject path")

    first_part = path.first_part
    if isinstance(first_part, AttributePathPart):
        if not isinstance(root, ClassNode):
            raise ValueError("Attribute paths need a class pattern parent")
        attributes = dict(root.attributes)
        child = attributes.get(first_part.name, WildcardNode())
        attributes[first_part.name] = insert_node(child, path.tail(), node)
        return ClassNode(root.classes, tuple(attributes.items()))
    if isinstance(first_part, SubscriptPathPart):
        if not isinstance(root, SequenceNode):
            raise ValueError("Subscript paths need a sequence pattern parent")
        elements = dict(root.elements)
        child = elements.get(first_part.index, WildcardNode())
        elements[first_part.index] = insert_node(child, path.tail(), node)
        return SequenceNode(root.length, root.use_star, tuple(elements.items()))
    # AccessPathPart is a closed union of attribute and subscript parts.
    raise ValueError("Unsupported subject path part")  # pragma: no cover


def insert_capture_node(
    root: PatternNode, path: AccessPath, node: CaptureNode
) -> PatternNode | None:
    if path.is_subject:
        return node if isinstance(root, WildcardNode) else None
    if isinstance(root, OrNode):
        alternatives = tuple(
            insert_capture_node(alternative, path, node)
            for alternative in root.alternatives
        )
        if any(alternative is None for alternative in alternatives):
            return None
        return OrNode(
            tuple(
                alternative for alternative in alternatives if alternative is not None
            )
        )

    first_part = path.first_part
    if isinstance(first_part, AttributePathPart):
        if not isinstance(root, ClassNode):
            return None
        attributes = dict(root.attributes)
        child = attributes.get(first_part.name)
        if child is None:
            return None
        inserted = insert_capture_node(child, path.tail(), node)
        if inserted is None:
            return None
        attributes[first_part.name] = inserted
        return ClassNode(root.classes, tuple(attributes.items()))

    if isinstance(first_part, SubscriptPathPart):
        if not isinstance(root, SequenceNode):
            return None
        elements = dict(root.elements)
        child = elements.get(first_part.index)
        if child is None:
            if not path.tail().is_subject:
                return None
            elements[first_part.index] = node
        else:
            inserted = insert_capture_node(child, path.tail(), node)
            if inserted is None:
                return None
            elements[first_part.index] = inserted
        return SequenceNode(root.length, root.use_star, tuple(elements.items()))

    return None


def render_child_node(node: PatternNode) -> cst.MatchPattern:
    pattern = node.render()
    return (
        bracket_sequence_pattern(pattern)
        if isinstance(node, SequenceNode) and isinstance(pattern, cst.MatchList)
        else pattern
    )


def bracket_sequence_pattern(pattern: cst.MatchList) -> cst.MatchList:
    patterns = pattern.patterns
    if len(patterns) == 1:
        patterns = [cst.MatchSequenceElement(value=patterns[0].value)]
    return pattern.with_changes(
        patterns=patterns,
        lbracket=cst.LeftSquareBracket(),
        rbracket=cst.RightSquareBracket(),
    )
