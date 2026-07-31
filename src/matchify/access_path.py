"""Absolute and match-subject-bound expression access paths."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst


def extract_integer_subscript_index(subscript: cst.Subscript) -> int | None:
    """Return the integer index for simple subscripts like `x[0]`."""
    if len(subscript.slice) != 1:
        return None
    slice_elem = subscript.slice[0]
    if not isinstance(slice_elem.slice, cst.Index):
        return None
    index_val = slice_elem.slice.value
    if not isinstance(index_val, cst.Integer):
        return None
    return int(index_val.value)


@dataclass(frozen=True)
class AttributePathPart:
    name: str


@dataclass(frozen=True)
class SubscriptPathPart:
    index: int | None
    expression_key: str | None = None


@dataclass(frozen=True)
class NameRoot:
    """Root of an access path that has not been bound to a match subject."""

    name: str


@dataclass(frozen=True)
class MatchSubjectRoot:
    """Root of an access path bound to one match subject."""


@dataclass(frozen=True)
class ExpressionRoot:
    """Root expression that is not a plain name, compared by source shape."""

    code: str


PathRoot = NameRoot | ExpressionRoot | MatchSubjectRoot
AccessPathPart = AttributePathPart | SubscriptPathPart


@dataclass(frozen=True)
class AccessPath:
    """A statically representable expression access path.

    Examples:
        node             -> NameRoot("node"), ()
        node.value       -> NameRoot("node"), (AttributePathPart("value"),)
        bound node.value -> MatchSubjectRoot(), (AttributePathPart("value"),)
    """

    root: PathRoot
    parts: tuple[AccessPathPart, ...] = ()

    @classmethod
    def from_expression(cls, node: cst.BaseExpression) -> AccessPath:
        parts: list[AccessPathPart] = []
        current = node

        while True:
            if isinstance(current, cst.Name):
                return cls(NameRoot(current.value), tuple(reversed(parts)))
            if isinstance(current, cst.Attribute):
                parts.append(AttributePathPart(current.attr.value))
                current = current.value
                continue
            if isinstance(current, cst.Subscript):
                index = extract_integer_subscript_index(current)
                parts.append(
                    SubscriptPathPart(
                        index,
                        expression_key=(
                            None
                            if index is not None
                            else cst.Module([]).code_for_node(current)
                        ),
                    )
                )
                current = current.value
                continue
            return cls(
                ExpressionRoot(cst.Module([]).code_for_node(current)),
                tuple(reversed(parts)),
            )

    def bind(
        self,
        subject: AccessPath,
        target: tuple[AccessPathPart, ...] = (),
    ) -> AccessPath:
        """Replace a matching subject prefix with a bound target prefix."""
        if not self.starts_with(subject):
            return self
        return AccessPath(
            MatchSubjectRoot(),
            (*target, *self.parts[len(subject.parts) :]),
        )

    @classmethod
    def common_prefix(cls, paths: tuple[AccessPath, ...]) -> AccessPath | None:
        if not paths or any(path.root != paths[0].root for path in paths[1:]):
            return None
        common_parts = []
        for parts in zip(*(path.parts for path in paths)):
            if any(part != parts[0] for part in parts[1:]):
                break
            common_parts.append(parts[0])
        return cls(paths[0].root, tuple(common_parts))

    def to_expression(self) -> cst.BaseExpression:
        """Build fresh CST for an unbound access path."""
        if isinstance(self.root, NameRoot):
            expression: cst.BaseExpression = cst.Name(self.root.name)
        elif isinstance(self.root, ExpressionRoot):
            expression = cst.parse_expression(self.root.code)
        else:
            raise ValueError("A bound access path cannot be rendered as a subject")

        for part in self.parts:
            if isinstance(part, AttributePathPart):
                expression = cst.Attribute(value=expression, attr=cst.Name(part.name))
            elif part.index is not None:
                expression = cst.Subscript(
                    value=expression,
                    slice=[
                        cst.SubscriptElement(
                            slice=cst.Index(cst.Integer(str(part.index)))
                        )
                    ],
                )
            elif part.expression_key is not None:
                expression = cst.parse_expression(part.expression_key)
            else:  # pragma: no cover
                raise ValueError("An unknown subscript needs an expression key")
        return expression

    @property
    def is_bound(self) -> bool:
        return isinstance(self.root, MatchSubjectRoot)

    @property
    def is_subject(self) -> bool:
        return self.is_bound and not self.parts

    @property
    def is_composite_subject(self) -> bool:
        """Whether this path is one top-level slot of a composite subject."""
        return (
            self.is_bound
            and len(self.parts) == 1
            and isinstance(self.parts[0], SubscriptPathPart)
            and self.parts[0].index is not None
        )

    @property
    def is_patternable(self) -> bool:
        return self.is_bound and all(
            not isinstance(part, SubscriptPathPart) or part.index is not None
            for part in self.parts
        )

    @property
    def contains_subscript(self) -> bool:
        return any(isinstance(part, SubscriptPathPart) for part in self.parts)

    @property
    def first_part(self) -> AccessPathPart | None:
        return self.parts[0] if self.parts else None

    def tail(self) -> AccessPath:
        return AccessPath(self.root, self.parts[1:])

    def parent(self) -> AccessPath:
        return AccessPath(self.root, self.parts[:-1])

    def starts_with(self, prefix: AccessPath) -> bool:
        return (
            self.root == prefix.root and self.parts[: len(prefix.parts)] == prefix.parts
        )

    def strip_prefix(self, prefix: AccessPath) -> AccessPath:
        if not self.starts_with(prefix):
            raise ValueError("Cannot strip a path that is not a prefix")
        return AccessPath(self.root, self.parts[len(prefix.parts) :])

    def first_part_after(self, prefix: AccessPath) -> AccessPathPart | None:
        if not self.starts_with(prefix):
            return None
        index = len(prefix.parts)
        return self.parts[index] if index < len(self.parts) else None


@dataclass(frozen=True)
class MatchSubjectPlan:
    """Ordered subjects and their relative locations in one match value."""

    subjects: tuple[AccessPath, ...]

    @classmethod
    def from_subjects(cls, subjects: tuple[AccessPath, ...]) -> MatchSubjectPlan:
        if not subjects:
            raise ValueError("A match subject plan needs at least one subject")
        for index, subject in enumerate(subjects):
            if any(
                subject.starts_with(other) or other.starts_with(subject)
                for other in subjects[index + 1 :]
            ):
                raise ValueError("Match subjects must not overlap")
        return cls(subjects)

    @classmethod
    def from_aligned_candidates(
        cls, candidates: tuple[tuple[AccessPath, ...], ...]
    ) -> MatchSubjectPlan | None:
        if not candidates or not candidates[0]:
            return None
        size = len(candidates[0])
        if any(len(paths) != size for paths in candidates[1:]):
            return None
        subjects = tuple(
            AccessPath.common_prefix(tuple(paths[index] for paths in candidates))
            for index in range(size)
        )
        if any(subject is None for subject in subjects):
            return None
        return cls._from_optional_subjects(subjects)

    @classmethod
    def from_shared_candidates(
        cls, candidates: tuple[tuple[AccessPath, ...], ...]
    ) -> MatchSubjectPlan | None:
        if not candidates or not candidates[0]:
            return None
        subjects = []
        for first in candidates[0]:
            if any(subject.root == first.root for subject in subjects):
                continue
            matching_groups = tuple(
                tuple(path for path in paths if path.root == first.root)
                for paths in candidates
            )
            if any(not group for group in matching_groups):
                continue
            subject = AccessPath.common_prefix(
                tuple(path for group in matching_groups for path in group)
            )
            if subject is not None:
                subjects.append(subject)
        return cls._from_optional_subjects(tuple(subjects))

    @classmethod
    def from_majority_candidates(
        cls, candidates: tuple[tuple[AccessPath, ...], ...]
    ) -> MatchSubjectPlan | None:
        """Build a plan from roots used by more than half of the branches."""
        if not candidates:
            return None

        roots = []
        for paths in candidates:
            for path in paths:
                if path.root not in roots:
                    roots.append(path.root)

        subjects = []
        for root in roots:
            matching_groups = tuple(
                tuple(path for path in paths if path.root == root)
                for paths in candidates
            )
            present_groups = tuple(group for group in matching_groups if group)
            if len(present_groups) * 2 <= len(candidates):
                continue
            subject = AccessPath.common_prefix(
                tuple(path for group in present_groups for path in group)
            )
            if subject is not None:
                subjects.append(subject)
        return cls._from_optional_subjects(tuple(subjects))

    @classmethod
    def _from_optional_subjects(
        cls, subjects: tuple[AccessPath | None, ...]
    ) -> MatchSubjectPlan | None:
        concrete = tuple(subject for subject in subjects if subject is not None)
        if len(concrete) != len(subjects) or not concrete:
            return None
        try:
            return cls.from_subjects(concrete)
        except ValueError:
            return None

    @property
    def is_composite(self) -> bool:
        return len(self.subjects) > 1

    def bind(self, path: AccessPath) -> AccessPath:
        for index, subject in enumerate(self.subjects):
            if path.starts_with(subject):
                target = () if not self.is_composite else (SubscriptPathPart(index),)
                return path.bind(subject, target)
        return path

    def to_expression(self) -> cst.BaseExpression:
        expressions = tuple(subject.to_expression() for subject in self.subjects)
        if len(expressions) == 1:
            return expressions[0]
        return cst.Tuple(
            elements=[cst.Element(expression) for expression in expressions]
        )
