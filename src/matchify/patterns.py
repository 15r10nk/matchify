"""Shared pattern construction and condition helpers."""

import re

import libcst as cst
from libcst import matchers as m


def flatten_boolean(
    node: cst.BaseExpression,
    operator_type: type[cst.BaseBooleanOp] | None = None,
) -> list[cst.BaseExpression]:
    if isinstance(node, cst.BooleanOperation) and (
        operator_type is None or isinstance(node.operator, operator_type)
    ):
        return flatten_boolean(node.left, operator_type) + flatten_boolean(
            node.right, operator_type
        )
    return [node]


def is_singleton_name(node: cst.BaseExpression) -> bool:
    return m.matches(
        node, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")
    )


def is_literal_value(node: cst.BaseExpression) -> bool:
    if isinstance(node, cst.UnaryOperation) and isinstance(
        node.operator, (cst.Minus, cst.Plus)
    ):
        return isinstance(node.expression, (cst.Integer, cst.Float))

    return is_singleton_name(node) or m.matches(
        node,
        m.Integer() | m.Float() | m.SimpleString() | m.ConcatenatedString(),
    )


def is_value_pattern_expr(node: cst.BaseExpression) -> bool:
    """Return whether an expression can be rendered as a match value pattern."""
    return is_literal_value(node) or is_qualified_value_expr(node)


def is_qualified_value_expr(node: cst.BaseExpression) -> bool:
    """Return whether an expression is a dotted name that cannot capture."""
    if isinstance(node, cst.Attribute):
        return isinstance(node.value, cst.Name) or is_qualified_value_expr(node.value)
    return False


def is_isinstance_call(node: cst.CSTNode) -> bool:
    return isinstance(node, cst.Call) and m.matches(
        node, m.Call(func=m.Name(value="isinstance"), args=[m.Arg(), m.Arg()])
    )


def is_len_call(node: cst.CSTNode) -> bool:
    return isinstance(node, cst.Call) and m.matches(
        node, m.Call(func=m.Name(value="len"), args=[m.Arg()])
    )


def build_value_pattern(value: cst.BaseExpression) -> cst.MatchPattern:
    if (
        isinstance(value, cst.UnaryOperation)
        and isinstance(value.operator, cst.Plus)
        and isinstance(value.expression, (cst.Integer, cst.Float))
    ):
        value = value.expression
    if is_singleton_name(value):
        return cst.MatchSingleton(value=value)
    return cst.MatchValue(value=value)


def build_wildcard_pattern() -> cst.MatchAs:
    return cst.MatchAs(pattern=None, name=None)


def build_or_pattern(patterns: list[cst.MatchPattern]) -> cst.MatchPattern:
    if len(patterns) == 1:
        return patterns[0]

    elements = [
        cst.MatchOrElement(
            pattern=pattern,
            separator=cst.BitOr() if index < len(patterns) - 1 else None,
        )
        for index, pattern in enumerate(patterns)
    ]
    return cst.MatchOr(patterns=elements)


def extract_isinstance_classes(
    class_arg: cst.BaseExpression, ignore_types_pattern: str | None
) -> tuple[cst.BaseExpression, ...] | None:
    if is_ignored_type_expr(class_arg, ignore_types_pattern):
        return None
    if isinstance(class_arg, cst.Tuple):
        if any(
            isinstance(element, cst.StarredElement)
            or is_ignored_type_expr(element.value, ignore_types_pattern)
            for element in class_arg.elements
        ):
            return None
        return tuple(element.value for element in class_arg.elements) or None
    return (class_arg,)


def is_class_pattern_expr(expr: cst.BaseExpression) -> bool:
    """Return whether an expression is valid before ``()`` in a class pattern."""
    if isinstance(expr, cst.Name):
        return True
    if isinstance(expr, cst.Attribute):
        return is_class_pattern_expr(expr.value)
    return False


def is_none_type_expr(expr: cst.BaseExpression) -> bool:
    """Return whether an expression is exactly ``type(None)``."""
    return m.matches(
        expr,
        m.Call(
            func=m.Name(value="type"),
            args=[m.Arg(value=m.Name(value="None"))],
        ),
    )


def is_ignored_type_expr(
    expr: cst.BaseExpression, ignore_types_pattern: str | None
) -> bool:
    return (
        ignore_types_pattern is not None
        and isinstance(expr, cst.Name)
        and re.match(ignore_types_pattern, expr.value) is not None
    )


def build_class_pattern(
    classes: tuple[cst.BaseExpression, ...],
    keyword_patterns: list[tuple[str, cst.MatchPattern]] | None = None,
) -> cst.MatchPattern:
    kwds = [
        cst.MatchKeywordElement(key=cst.Name(name), pattern=pattern)
        for name, pattern in (keyword_patterns or [])
    ]
    patterns = [
        cst.MatchClass(
            cls=class_expr.with_changes(lpar=(), rpar=()),
            patterns=[],
            kwds=kwds,
        )
        for class_expr in classes
    ]
    return build_or_pattern(patterns)
