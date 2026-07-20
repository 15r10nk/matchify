"""Safety checks that decide whether a condition can be converted."""

import libcst as cst

from .patterns import flatten_boolean, is_len_call, is_literal_value, is_singleton_name


def is_safe_condition(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
) -> bool:
    for component in flatten_boolean(condition):
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
            elif is_len_call(component.left):
                len_call = component.left
                len_arg = len_call.args[0].value
                if (
                    isinstance(subject, cst.Attribute)
                    and isinstance(len_arg, cst.Attribute)
                    and len_arg.value.deep_equals(subject)
                ):
                    return False

    return True
