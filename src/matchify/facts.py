"""Normalized branch facts used as a bridge toward a recursive pattern IR."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst

from .patterns import build_class_pattern, build_or_pattern, build_value_pattern
from .sequence_patterns import (
    RawElementPattern,
    SequenceElementPattern,
    WildcardElementPattern,
    build_sequence_match_list,
    validate_wildcard_constraint,
)
from .subject_path import (
    AttributePathPart,
    SubjectPath,
    SubscriptPathPart,
)


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
    alternatives: tuple[ValueFact | ClassFact | tuple[PathFact, ...], ...]


PathFact = ValueFact | ClassFact | SequenceFact | OrFact


class PatternNode:
    """Base class for explicit recursive match-pattern IR nodes."""

    # Abstract base hook; concrete node classes are covered through E2E transforms.
    def render(self) -> cst.MatchPattern:  # pragma: no cover
        raise NotImplementedError

    def insert(self, path: SubjectPath, node: PatternNode) -> PatternNode:
        return insert_node(self, path, node)


@dataclass(frozen=True)
class WildcardNode(PatternNode):
    """Wildcard placeholder used when a path creates an intermediate child."""

    # Placeholder nodes should be replaced before rendering through public flows.
    def render(self) -> cst.MatchPattern:  # pragma: no cover
        return cst.MatchAs(pattern=None, name=None)


@dataclass(frozen=True)
class ValueNode(PatternNode):
    """A literal or singleton value pattern."""

    value: cst.BaseExpression

    def render(self) -> cst.MatchPattern:
        return build_value_pattern(self.value)


@dataclass(frozen=True)
class CaptureNode(PatternNode):
    """A capture pattern that binds one sequence element."""

    name: str

    def render(self) -> cst.MatchPattern:
        return cst.MatchAs(pattern=None, name=cst.Name(self.name))


@dataclass(frozen=True)
class ClassNode(PatternNode):
    """A class pattern with recursively nested attribute children."""

    classes: tuple[cst.BaseExpression, ...]
    attributes: tuple[tuple[str, PatternNode], ...] = ()

    def render(self) -> cst.MatchPattern:
        # Intermediate class nodes without classes are never rendered by the
        # public transformer; anchors must fill the class before rendering.
        if not self.classes:  # pragma: no cover
            raise ValueError("Class pattern nodes need class expressions before render")
        return build_class_pattern(
            list(self.classes),
            [(name, render_child_node(node)) for name, node in self.attributes],
        )

    def insert_attribute(
        self, name: str, path: SubjectPath, node: PatternNode
    ) -> ClassNode:
        attributes = dict(self.attributes)
        child = attributes.get(name, WildcardNode())
        attributes[name] = child.insert(path, node)
        return ClassNode(self.classes, tuple(attributes.items()))


@dataclass(frozen=True)
class SequenceNode(PatternNode):
    """A sequence pattern with recursively nested element children."""

    length: int
    use_star: bool = False
    elements: tuple[tuple[int, PatternNode], ...] = ()

    def render(self) -> cst.MatchPattern:
        elements = dict(self.elements)
        required_len = self.length
        if self.use_star and elements:
            required_len = max(elements) + 1

        if not self.use_star and elements and max(elements) >= required_len:
            raise ValueError("Sequence element facts exceed the checked length")
        if not self.use_star and not validate_wildcard_constraint(
            {
                index: RawElementPattern(node.render())
                for index, node in elements.items()
            },
            required_len,
        ):
            raise ValueError("Sequence fact would produce too many wildcards")

        pattern_infos: list[SequenceElementPattern] = [
            (
                RawElementPattern(render_child_node(elements[index]))
                if index in elements
                else WildcardElementPattern()
            )
            for index in range(required_len)
        ]
        return build_sequence_match_list(pattern_infos, use_star=self.use_star)

    def insert_element(
        self, index: int, path: SubjectPath, node: PatternNode
    ) -> SequenceNode:
        elements = dict(self.elements)
        child = elements.get(index, WildcardNode())
        elements[index] = child.insert(path, node)
        return SequenceNode(self.length, self.use_star, tuple(elements.items()))


@dataclass(frozen=True)
class OrNode(PatternNode):
    """An OR pattern with recursive alternatives."""

    alternatives: tuple[PatternNode, ...]

    def render(self) -> cst.MatchPattern:
        return build_or_pattern(
            [bracket_or_sequence_pattern(node.render()) for node in self.alternatives]
        )

    def insert(self, path: SubjectPath, node: PatternNode) -> PatternNode:
        # Merging a second subject-level fact into an OR node is an internal
        # conflict-resolution path; generated branches avoid this shape.
        if path.is_subject:  # pragma: no cover
            return merge_nodes(self, node)
        return OrNode(
            tuple(alternative.insert(path, node) for alternative in self.alternatives)
        )


@dataclass(frozen=True)
class PatternTree:
    """Small wrapper around the explicit recursive pattern-node IR."""

    node: PatternNode

    @classmethod
    def from_facts(
        cls,
        facts: tuple[PathFact, ...],
        *,
        capture_facts: tuple[CaptureFact, ...] = (),
    ) -> PatternTree:
        # Public normalization only builds PatternTree after at least one fact.
        if not facts:  # pragma: no cover
            raise ValueError("PatternTree needs at least one fact")

        root: PatternNode | None = None
        for fact in facts:
            root = insert_fact(root, fact)

        # Defensive only: non-empty facts always assign a root or raise earlier.
        if root is None:  # pragma: no cover
            raise ValueError("PatternTree has no renderable node")

        tree = cls(root)
        return tree.with_captures(capture_facts)

    def with_captures(self, capture_facts: tuple[CaptureFact, ...]) -> PatternTree:
        tree = self
        for fact in capture_facts:
            tree = PatternTree(
                insert_capture_node(
                    tree.node,
                    capture_path(fact),
                    CaptureNode(fact.name),
                )
            )
        return tree

    def render(self) -> cst.MatchPattern:
        return self.node.render()


@dataclass(frozen=True)
class BranchFacts:
    """Normalized facts for one branch condition."""

    condition: cst.BaseExpression
    subject: cst.BaseExpression
    facts: tuple[PathFact, ...]
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
    def from_facts(
        cls,
        condition: cst.BaseExpression,
        subject: cst.BaseExpression,
        facts: tuple[PathFact, ...],
        *,
        guard: cst.BaseExpression | None = None,
    ) -> BranchFacts:
        return cls(
            condition=condition,
            subject=subject,
            facts=facts,
            pattern=PatternTree.from_facts(facts),
            guard=guard,
        )


def insert_fact(root: PatternNode | None, fact: PathFact) -> PatternNode:
    node = node_from_fact(fact)
    if root is None:
        # The builder orders facts so the first one always anchors the subject.
        if not fact.path.is_subject:  # pragma: no cover
            raise ValueError("First pattern fact must describe the subject")
        return node
    return root.insert(fact.path, node)


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


def insert_node(root: PatternNode, path: SubjectPath, node: PatternNode) -> PatternNode:
    if path.is_subject:
        return merge_nodes(root, node)

    first_part = path.first_part
    if isinstance(first_part, AttributePathPart):
        # Wildcard-to-class promotion is defensive for future nested fact shapes;
        # current public normalization requires class anchors before attributes.
        if isinstance(root, WildcardNode):  # pragma: no cover
            root = ClassNode(())
        # Normalized attribute paths are only inserted below class-compatible nodes.
        if not isinstance(root, ClassNode):  # pragma: no cover
            raise ValueError("Attribute paths need a class pattern parent")
        return root.insert_attribute(first_part.name, path.tail(), node)
    if isinstance(first_part, SubscriptPathPart):
        # Wildcard-to-sequence promotion is retained for defensive recursive
        # insertion; public normalization creates sequence anchors explicitly.
        if isinstance(root, WildcardNode):  # pragma: no cover
            root = SequenceNode(0, use_star=True)
        # Normalized subscript paths are only inserted below sequence-compatible nodes.
        if not isinstance(root, SequenceNode):  # pragma: no cover
            raise ValueError("Subscript paths need a sequence pattern parent")
        return root.insert_element(first_part.index, path.tail(), node)
    # SubjectPathPart is a closed union of attribute and subscript parts.
    raise ValueError("Unsupported subject path part")  # pragma: no cover


def merge_nodes(existing: PatternNode, incoming: PatternNode) -> PatternNode:
    # The following fallbacks protect manual/future fact combinations; current
    # end-to-end paths construct compatible anchors before merging.
    if isinstance(existing, WildcardNode):  # pragma: no cover
        return incoming
    if isinstance(incoming, WildcardNode):  # pragma: no cover
        return existing
    if isinstance(existing, CaptureNode) or isinstance(
        incoming, CaptureNode
    ):  # pragma: no cover
        return incoming
    if isinstance(existing, ValueNode) or isinstance(
        incoming, ValueNode
    ):  # pragma: no cover
        return incoming
    if isinstance(existing, ClassNode) and isinstance(
        incoming, ClassNode
    ):  # pragma: no cover
        return merge_class_nodes(existing, incoming)
    if isinstance(existing, SequenceNode) and isinstance(
        incoming, SequenceNode
    ):  # pragma: no cover
        return merge_sequence_nodes(existing, incoming)
    if isinstance(existing, OrNode) and isinstance(
        incoming, OrNode
    ):  # pragma: no cover
        return incoming
    return incoming  # pragma: no cover


def merge_class_nodes(  # pragma: no cover
    existing: ClassNode, incoming: ClassNode
) -> ClassNode:
    # Retained for overlapping class facts from future predicate builders; current
    # E2E flows avoid duplicate class facts on one path.
    attributes = dict(existing.attributes)
    for name, incoming_child in incoming.attributes:
        if name in attributes:
            attributes[name] = merge_nodes(attributes[name], incoming_child)
        else:
            attributes[name] = incoming_child
    return ClassNode(incoming.classes, tuple(attributes.items()))


def merge_sequence_nodes(
    existing: SequenceNode, incoming: SequenceNode
) -> SequenceNode:  # pragma: no cover
    # Retained for overlapping sequence facts from future predicate builders;
    # current E2E flows reject duplicate length facts before rendering.
    elements = dict(existing.elements)
    for index, incoming_child in incoming.elements:
        if index in elements:
            elements[index] = merge_nodes(elements[index], incoming_child)
        else:
            elements[index] = incoming_child
    return SequenceNode(incoming.length, incoming.use_star, tuple(elements.items()))


def capture_path(fact: CaptureFact) -> SubjectPath:
    return SubjectPath((*fact.path.parts, SubscriptPathPart(fact.index)))


def insert_capture_node(
    root: PatternNode, path: SubjectPath, node: CaptureNode
) -> PatternNode:
    # Capture facts always target a subscript path in public transformations.
    if path.is_subject:  # pragma: no cover
        return merge_nodes(root, node)
    if isinstance(root, OrNode):
        return OrNode(
            tuple(
                insert_capture_node(alternative, path, node)
                for alternative in root.alternatives
            )
        )

    first_part = path.first_part
    if isinstance(first_part, AttributePathPart):
        # Invalid capture paths are left unchanged; public captures into
        # attributes only occur below class patterns.
        if not isinstance(root, ClassNode):  # pragma: no cover
            return root
        attributes = dict(root.attributes)
        child = attributes.get(first_part.name)
        if child is None:
            return root
        attributes[first_part.name] = insert_capture_node(child, path.tail(), node)
        return ClassNode(root.classes, tuple(attributes.items()))

    if isinstance(first_part, SubscriptPathPart):
        # Invalid capture paths are left unchanged; E2E tests cover the common
        # attribute-missing case, this is the non-sequence defensive twin.
        if not isinstance(root, SequenceNode):  # pragma: no cover
            return root
        elements = dict(root.elements)
        child = elements.get(first_part.index)
        if child is None:
            if not path.tail().is_subject:
                return root
            elements[first_part.index] = node
        else:
            elements[first_part.index] = insert_capture_node(child, path.tail(), node)
        return SequenceNode(root.length, root.use_star, tuple(elements.items()))

    # SubjectPathPart is a closed union; retained for defensive future edits.
    return root  # pragma: no cover


def render_child_node(node: PatternNode) -> cst.MatchPattern:
    pattern = node.render()
    if isinstance(node, SequenceNode) and isinstance(pattern, cst.MatchList):
        return bracket_sequence_pattern(pattern)
    return pattern


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
