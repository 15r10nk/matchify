"""Sequence-pattern recognition and construction."""

import libcst as cst

from .patterns import flatten_boolean, is_isinstance_call, is_len_call
from .subject_path import SubjectPath


def find_sequence_subject(test: cst.BaseExpression) -> cst.BaseExpression | None:
    for component in flatten_boolean(test, cst.And):
        if not isinstance(component, cst.Comparison) or len(component.comparisons) != 1:
            continue
        target = component.comparisons[0]
        if not isinstance(target.operator, (cst.Equal, cst.GreaterThanEqual)):
            continue
        if not isinstance(target.comparator, cst.Integer):
            continue
        if not is_len_call(component.left):
            continue
        len_call = component.left
        subject = len_call.args[0].value
        if has_direct_sequence_element_check(test, subject):
            return subject
        return None

    return None


def has_direct_sequence_element_check(
    test: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    for component in flatten_boolean(test, cst.And):
        if isinstance(component, cst.BooleanOperation) and isinstance(
            component.operator, cst.Or
        ):
            if all(
                has_direct_sequence_element_check(part, subject)
                for part in flatten_boolean(component, cst.Or)
            ):
                return True
        if isinstance(component, cst.Comparison):
            path = SubjectPath.from_expression(component.left, subject)
            if path is not None and path.starts_with_subscript:
                return True
        if is_isinstance_call(component):
            # False sides are just "not a direct sequence element" probes while
            # scanning mixed AND components.
            if (  # pragma: no branch
                path := SubjectPath.from_expression(component.args[0].value, subject)
            ) is not None and path.starts_with_subscript:
                return True
    return False


def build_sequence_match_list(
    pattern_infos: list[cst.MatchPattern | None],
    use_star: bool,
) -> cst.MatchList:
    elements = [
        cst.MatchSequenceElement(
            value=(
                cst.MatchAs(pattern=None, name=None)
                if pattern_info is None
                else pattern_info
            ),
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
        )
        for pattern_info in pattern_infos
    ]

    if use_star:
        elements.append(
            cst.MatchSequenceElement(value=cst.MatchStar(name=cst.Name("_")))
        )
        return cst.MatchList(patterns=elements, lbracket=None, rbracket=None)

    if len(elements) > 1:
        elements[-1] = cst.MatchSequenceElement(value=elements[-1].value)
    elif elements:  # pragma: no branch
        elements[-1] = cst.MatchSequenceElement(
            value=elements[-1].value,
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace("")),
        )
    return cst.MatchList(patterns=elements, lbracket=None, rbracket=None)
