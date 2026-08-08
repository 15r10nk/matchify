"""Safety checks that decide whether a condition can be converted."""

import libcst as cst
from libcst import matchers as m

from .access_path import AccessPath, AttributePathPart, MatchSubjectPlan
from .assumptions import Assumptions
from .patterns import (
    extract_isinstance_classes,
    flatten_boolean,
    is_len_call,
    is_singleton_name,
    is_value_pattern_expr,
)


def is_safe_condition(
    condition: cst.BaseExpression,
    subject: MatchSubjectPlan,
    *,
    ignore_types_pattern: str | None,
    assumptions: Assumptions,
) -> bool:
    for component in flatten_boolean(condition):
        if isinstance(component, cst.Comparison) and len(component.comparisons) == 1:
            target = component.comparisons[0]
            comparator = target.comparator
            left_path = AccessPath.from_expression(component.left)
            if left_path in subject.subjects:
                if isinstance(target.operator, cst.Equal) and not is_value_pattern_expr(
                    comparator
                ):
                    return False
                if isinstance(target.operator, cst.Is) and not is_singleton_name(
                    comparator
                ):
                    if not (
                        assumptions.identity_equality
                        and is_value_pattern_expr(comparator)
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

    return not has_problematic_isinstance(
        condition,
        subject,
        ignore_types_pattern=ignore_types_pattern,
    )


def has_problematic_isinstance(
    condition: cst.BaseExpression,
    subject: MatchSubjectPlan,
    *,
    ignore_types_pattern: str | None,
) -> bool:
    for call in m.findall(condition, m.Call(func=m.Name(value="isinstance"))):
        if len(call.args) < 2:
            return True
        if AccessPath.from_expression(call.args[0].value) not in subject.subjects:
            continue
        if extract_isinstance_classes(call.args[1].value, ignore_types_pattern) is None:
            return True
    return False
