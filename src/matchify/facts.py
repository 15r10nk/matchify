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
    alternatives: tuple[ValueFact | ClassFact | PatternTree, ...]


PathFact = ValueFact | ClassFact | SequenceFact | OrFact
BranchFact = PathFact


class PatternNode:
    """Base class for explicit recursive match-pattern IR nodes."""

    def render(self) -> cst.MatchPattern:
        raise NotImplementedError

    def insert(self, path: SubjectPath, node: PatternNode) -> PatternNode:
        return insert_node(self, path, node)


@dataclass(frozen=True)
class WildcardNode(PatternNode):
    """Wildcard placeholder used when a path creates an intermediate child."""

    def render(self) -> cst.MatchPattern:
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
        if not self.classes:
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
        if path.is_subject:
            return merge_nodes(self, node)
        return OrNode(
            tuple(alternative.insert(path, node) for alternative in self.alternatives)
        )


@dataclass(frozen=True)
class PatternTree:
    """Small wrapper around the explicit recursive pattern-node IR."""

    node: PatternNode

    @classmethod
    def from_value_fact(cls, fact: ValueFact) -> PatternTree:
        return cls.from_facts((fact,))

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
        return cls.from_facts(
            (fact, *sequence_facts, *or_facts, *value_facts, *class_facts),
            capture_facts=capture_facts,
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
        return cls.from_facts(
            (fact, *or_facts, *sequence_facts, *value_facts, *class_facts),
            capture_facts=capture_facts,
        )

    @classmethod
    def from_or_patterns(cls, patterns: tuple[PatternTree, ...]) -> PatternTree:
        return cls(OrNode(tuple(pattern.node for pattern in patterns)))

    @classmethod
    def from_facts(
        cls,
        facts: tuple[PathFact, ...],
        *,
        capture_facts: tuple[CaptureFact, ...] = (),
    ) -> PatternTree:
        if not facts:
            raise ValueError("PatternTree needs at least one fact")

        root: PatternNode | None = None
        for fact in facts:
            root = insert_fact(root, fact)

        if root is None:
            raise ValueError("PatternTree has no renderable node")

        tree = cls(root)
        return tree.with_captures(capture_facts)

    def insert(self, path: SubjectPath, node: PatternNode) -> PatternTree:
        return PatternTree(self.node.insert(path, node))

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


def insert_fact(root: PatternNode | None, fact: PathFact) -> PatternNode:
    node = node_from_fact(fact)
    if root is None:
        if not fact.path.is_subject:
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
    alternative: ValueFact | ClassFact | PatternTree,
) -> PatternNode:
    if isinstance(alternative, ValueFact):
        return ValueNode(alternative.value)
    if isinstance(alternative, ClassFact):
        return ClassNode(alternative.classes)
    return alternative.node


def insert_node(root: PatternNode, path: SubjectPath, node: PatternNode) -> PatternNode:
    if path.is_subject:
        return merge_nodes(root, node)

    first_part = path.first_part
    if isinstance(first_part, AttributePathPart):
        if isinstance(root, WildcardNode):
            root = ClassNode(())
        if not isinstance(root, ClassNode):
            raise ValueError("Attribute paths need a class pattern parent")
        return root.insert_attribute(first_part.name, path.tail(), node)
    if isinstance(first_part, SubscriptPathPart):
        if isinstance(root, WildcardNode):
            root = SequenceNode(0, use_star=True)
        if not isinstance(root, SequenceNode):
            raise ValueError("Subscript paths need a sequence pattern parent")
        return root.insert_element(first_part.index, path.tail(), node)
    raise ValueError("Unsupported subject path part")


def merge_nodes(existing: PatternNode, incoming: PatternNode) -> PatternNode:
    if isinstance(existing, WildcardNode):
        return incoming
    if isinstance(incoming, WildcardNode):
        return existing
    if isinstance(existing, CaptureNode) or isinstance(incoming, CaptureNode):
        return incoming
    if isinstance(existing, ValueNode) or isinstance(incoming, ValueNode):
        return incoming
    if isinstance(existing, ClassNode) and isinstance(incoming, ClassNode):
        return merge_class_nodes(existing, incoming)
    if isinstance(existing, SequenceNode) and isinstance(incoming, SequenceNode):
        return merge_sequence_nodes(existing, incoming)
    if isinstance(existing, OrNode) and isinstance(incoming, OrNode):
        return incoming
    return incoming


def merge_class_nodes(existing: ClassNode, incoming: ClassNode) -> ClassNode:
    attributes = dict(existing.attributes)
    for name, incoming_child in incoming.attributes:
        if name in attributes:
            attributes[name] = merge_nodes(attributes[name], incoming_child)
        else:
            attributes[name] = incoming_child
    return ClassNode(incoming.classes, tuple(attributes.items()))


def merge_sequence_nodes(
    existing: SequenceNode, incoming: SequenceNode
) -> SequenceNode:
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
    if path.is_subject:
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
        if not isinstance(root, ClassNode):
            return root
        attributes = dict(root.attributes)
        child = attributes.get(first_part.name)
        if child is None:
            return root
        attributes[first_part.name] = insert_capture_node(child, path.tail(), node)
        return ClassNode(root.classes, tuple(attributes.items()))

    if isinstance(first_part, SubscriptPathPart):
        if not isinstance(root, SequenceNode):
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

    return root


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
