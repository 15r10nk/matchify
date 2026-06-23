"""Safety checks that decide whether a condition can be converted."""

from __future__ import annotations

import libcst as cst
from libcst import matchers as m

from .patterns import is_literal_value, is_singleton_name


def is_safe_condition(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> bool:
    for component in flatten_all_boolean(condition):
        if isinstance(component, cst.Comparison) and len(component.comparisons) == 1:
            target = component.comparisons[0]
            comparator = target.comparator
            if component.left.deep_equals(subject):
                if isinstance(target.operator, cst.Equal) and not is_literal_value(
                    comparator
                ):
                    return False
                if isinstance(target.operator, cst.Is) and not is_singleton_name(
                    comparator
                ):
                    return False
            elif isinstance(
                component.left, cst.Attribute
            ) and component.left.value.deep_equals(subject):
                if isinstance(
                    target.operator, (cst.Equal, cst.Is)
                ) and not is_literal_value(comparator):
                    return False
            elif is_len_call_on_nested_subject_attribute(component.left, subject):
                return False

    return True


def flatten_all_boolean(node: cst.BaseExpression) -> list[cst.BaseExpression]:
    if isinstance(node, cst.BooleanOperation):
        return flatten_all_boolean(node.left) + flatten_all_boolean(node.right)
    return [node]


def is_len_call_on_nested_subject_attribute(
    expr: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    if not m.matches(expr, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
        return False

    call = expr  # type: ignore[assignment]
    len_arg = call.args[0].value
    return (
        isinstance(subject, cst.Attribute)
        and isinstance(len_arg, cst.Attribute)
        and len_arg.value.deep_equals(subject)
    )
