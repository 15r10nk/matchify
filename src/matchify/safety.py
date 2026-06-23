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
    if has_isinstance_tuple_with_subject_attrs(condition, subject):
        return False

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


def has_isinstance_tuple_with_subject_attrs(
    condition: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    has_tuple_isinstance = False
    has_subject_attr_check = False

    for component in flatten_all_boolean(condition):
        if isinstance(component, cst.Call) and m.matches(
            component, m.Call(func=m.Name(value="isinstance"))
        ):
            if len(component.args) >= 2 and component.args[0].value.deep_equals(
                subject
            ):
                has_tuple_isinstance = isinstance(component.args[1].value, cst.Tuple)
        elif isinstance(component, cst.Comparison) and isinstance(
            component.left, cst.Attribute
        ):
            has_subject_attr_check = component.left.value.deep_equals(subject)

    return has_tuple_isinstance and has_subject_attr_check


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
