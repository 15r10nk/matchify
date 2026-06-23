"""Helpers for reasoning about expressions derived from a match subject."""

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


SubjectPathPart = AttributePathPart | SubscriptPathPart


@dataclass(frozen=True)
class SubjectPath:
    """Path from the match subject to a derived expression.

    Examples:
        subject          -> ()
        subject.node     -> (AttributePathPart("node"),)
        subject.args[0]  -> (AttributePathPart("args"), SubscriptPathPart(0))

    Keeping this analysis in one place makes recognizers easier to reason
    about: they can ask about paths instead of re-walking LibCST nodes.
    """

    parts: tuple[SubjectPathPart, ...]

    @classmethod
    def from_expression(
        cls, node: cst.BaseExpression, subject: cst.BaseExpression
    ) -> SubjectPath | None:
        parts: list[SubjectPathPart] = []
        current = node

        while True:
            if current.deep_equals(subject):
                return cls(tuple(reversed(parts)))
            if isinstance(current, cst.Attribute):
                parts.append(AttributePathPart(current.attr.value))
                current = current.value
                continue
            if isinstance(current, cst.Subscript):
                parts.append(
                    SubscriptPathPart(extract_integer_subscript_index(current))
                )
                current = current.value
                continue
            return None

    @property
    def is_subject(self) -> bool:
        return not self.parts

    @property
    def starts_with_subscript(self) -> bool:
        return bool(self.parts) and isinstance(self.parts[0], SubscriptPathPart)

    @property
    def attribute_names(self) -> tuple[str, ...] | None:
        names = []
        for part in self.parts:
            if not isinstance(part, AttributePathPart):
                return None
            names.append(part.name)
        return tuple(names) if names else None

    @property
    def direct_attribute_name(self) -> str | None:
        if len(self.parts) != 1 or not isinstance(self.parts[0], AttributePathPart):
            return None
        return self.parts[0].name
