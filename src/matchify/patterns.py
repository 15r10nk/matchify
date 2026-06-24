"""Shared pattern construction and condition helpers."""

from __future__ import annotations

import libcst as cst
from libcst import matchers as m


def flatten_boolean(
    node: cst.BaseExpression, operator_type: type[cst.BaseBooleanOp]
) -> list[cst.BaseExpression]:
    if isinstance(node, cst.BooleanOperation) and isinstance(
        node.operator, operator_type
    ):
        return flatten_boolean(node.left, operator_type) + flatten_boolean(
            node.right, operator_type
        )
    return [node]


def combine_guards(parts: list[cst.BaseExpression]) -> cst.BaseExpression | None:
    if not parts:
        return None

    guard = parts[0]
    for part in parts[1:]:
        guard = cst.BooleanOperation(left=guard, operator=cst.And(), right=part)
    return guard


def is_singleton_name(node: cst.BaseExpression) -> bool:
    return m.matches(
        node, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")
    )


def is_literal_value(node: cst.BaseExpression) -> bool:
    if m.matches(node, m.UnaryOperation(operator=m.Minus() | m.Plus())):
        unary = node  # type: ignore[assignment]
        return m.matches(unary.expression, m.Integer() | m.Float())

    return m.matches(
        node,
        m.Integer()
        | m.Float()
        | m.SimpleString()
        | m.ConcatenatedString()
        | m.Name(value="True")
        | m.Name(value="False")
        | m.Name(value="None"),
    )


def build_value_pattern(value: cst.BaseExpression) -> cst.MatchPattern:
    value = normalize_value_pattern_expression(value)
    if is_singleton_name(value):
        return cst.MatchSingleton(value=value)
    return cst.MatchValue(value=value)


def normalize_value_pattern_expression(value: cst.BaseExpression) -> cst.BaseExpression:
    if (
        isinstance(value, cst.UnaryOperation)
        and isinstance(value.operator, cst.Plus)
        and isinstance(value.expression, (cst.Integer, cst.Float))
    ):
        return value.expression
    return value


def build_or_pattern(patterns: list[cst.MatchPattern]) -> cst.MatchPattern:
    if len(patterns) == 1:
        return patterns[0]

    elements = []
    for index, pattern in enumerate(patterns):
        if index < len(patterns) - 1:
            elements.append(cst.MatchOrElement(pattern=pattern, separator=cst.BitOr()))
        else:
            elements.append(cst.MatchOrElement(pattern=pattern))
    return cst.MatchOr(patterns=elements)


def extract_isinstance_classes(
    class_arg: cst.BaseExpression, ignore_types_pattern: str | None
) -> list[cst.BaseExpression] | None:
    if is_ignored_type_expr(class_arg, ignore_types_pattern):
        return None
    if isinstance(class_arg, cst.Tuple):
        classes = []
        for element in class_arg.elements:
            if isinstance(element, cst.StarredElement):
                return None
            if not isinstance(element, cst.Element):
                return None
            if is_ignored_type_expr(element.value, ignore_types_pattern):
                return None
            classes.append(element.value)
        return classes or None
    return [class_arg]


def is_ignored_type_expr(
    expr: cst.BaseExpression, ignore_types_pattern: str | None
) -> bool:
    if ignore_types_pattern is None or not m.matches(expr, m.Name()):
        return False

    import re

    return re.match(ignore_types_pattern, expr.value) is not None  # type: ignore[attr-defined]


def build_class_pattern(
    classes: list[cst.BaseExpression],
    keyword_patterns: list[tuple[str, cst.MatchPattern]] | None = None,
) -> cst.MatchPattern:
    kwds = [
        cst.MatchKeywordElement(key=cst.Name(name), pattern=pattern)
        for name, pattern in (keyword_patterns or [])
    ]
    patterns = [
        cst.MatchClass(cls=class_expr, patterns=[], kwds=kwds) for class_expr in classes
    ]
    return build_or_pattern(patterns)
