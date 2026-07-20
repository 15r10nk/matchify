"""Safety checks that decide whether a condition can be converted."""

import libcst as cst

from .access_path import AccessPath, AttributePathPart, MatchSubjectPlan
from .patterns import flatten_boolean, is_len_call, is_literal_value, is_singleton_name


def is_safe_condition(
    condition: cst.BaseExpression,
    subject: MatchSubjectPlan,
) -> bool:
    for component in flatten_boolean(condition):
        if isinstance(component, cst.Comparison) and len(component.comparisons) == 1:
            target = component.comparisons[0]
            comparator = target.comparator
            left_path = AccessPath.from_expression(component.left)
            if left_path in subject.subjects:
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
                len_path = AccessPath.from_expression(len_call.args[0].value)
                if any(
                    candidate.parts
                    and isinstance(candidate.parts[-1], AttributePathPart)
                    and len_path.parts
                    and isinstance(len_path.parts[-1], AttributePathPart)
                    and len_path.parent() == candidate
                    for candidate in subject.subjects
                ):
                    return False

    return True
