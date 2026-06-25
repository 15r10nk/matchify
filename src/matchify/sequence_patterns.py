"""Sequence-pattern recognition and construction."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .patterns import flatten_boolean
from .subject_path import SubjectPath


@dataclass(frozen=True)
class WildcardElementPattern:
    """Sequence element with no constraint."""


@dataclass(frozen=True)
class RawElementPattern:
    """Already-built LibCST pattern used when another recognizer did the work."""

    pattern: cst.MatchPattern


SequenceElementPattern = WildcardElementPattern | RawElementPattern


def find_sequence_subject(test: cst.BaseExpression) -> cst.BaseExpression | None:
    subject: cst.BaseExpression | None = None
    for component in flatten_boolean(test, cst.And):
        if not isinstance(component, cst.Comparison) or len(component.comparisons) != 1:
            continue
        target = component.comparisons[0]
        if not isinstance(target.operator, (cst.Equal, cst.GreaterThanEqual)):
            continue
        if not isinstance(target.comparator, cst.Integer):
            continue
        if not m.matches(
            component.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])
        ):
            continue
        len_call = component.left  # type: ignore[assignment]
        subject = len_call.args[0].value
        break

    if subject is None or not has_direct_sequence_element_check(test, subject):
        return None
    return subject


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
        if isinstance(component, cst.Call) and m.matches(
            component, m.Call(func=m.Name(value="isinstance"))
        ):
            # False sides are just "not a direct sequence element" probes while
            # scanning mixed AND components.
            if (  # pragma: no branch
                len(component.args) >= 1
                and (
                    path := SubjectPath.from_expression(
                        component.args[0].value, subject
                    )
                )
                is not None
                and path.starts_with_subscript
            ):
                return True
    return False


def build_sequence_match_list(
    pattern_infos: list[SequenceElementPattern],
    use_star: bool,
    is_top_level: bool = True,
) -> cst.MatchList:
    elements = build_sequence_elements(pattern_infos, use_star, is_top_level)
    return cst.MatchList(patterns=elements, lbracket=None, rbracket=None)


def build_sequence_elements(
    pattern_infos: list[SequenceElementPattern], use_star: bool, is_top_level: bool
) -> list[cst.MatchSequenceElement]:
    elements = [
        cst.MatchSequenceElement(
            value=build_match_pattern_from_info(pattern_info),
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
        )
        for pattern_info in pattern_infos
    ]

    if use_star:
        elements.append(
            cst.MatchSequenceElement(value=cst.MatchStar(name=cst.Name("_")))
        )
        return elements

    if len(elements) > 1 or not is_top_level:
        last = elements[-1]
        elements[-1] = cst.MatchSequenceElement(value=last.value)
    elif elements:  # pragma: no branch
        last = elements[-1]
        elements[-1] = cst.MatchSequenceElement(
            value=last.value,
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace("")),
        )
    return elements


def build_match_pattern_from_info(
    pattern_info: SequenceElementPattern,
) -> cst.MatchPattern:
    if isinstance(pattern_info, WildcardElementPattern):
        return cst.MatchAs(pattern=None, name=None)
    if isinstance(pattern_info, RawElementPattern):
        return pattern_info.pattern
    raise TypeError(f"Unsupported sequence element pattern: {pattern_info!r}")


def validate_wildcard_constraint(
    elements: dict[int, SequenceElementPattern], total_len: int
) -> bool:
    consecutive_wildcards = 0
    for index in range(total_len):
        if index not in elements:
            consecutive_wildcards += 1
            if consecutive_wildcards >= 3:
                return False
        else:
            consecutive_wildcards = 0
    return True
