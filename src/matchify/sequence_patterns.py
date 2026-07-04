"""Sequence-pattern construction."""

import libcst as cst

from .patterns import build_wildcard_pattern


def build_sequence_match_list(
    pattern_infos: list[cst.MatchPattern | None],
    use_star: bool,
) -> cst.MatchList:
    elements = [
        cst.MatchSequenceElement(
            value=(build_wildcard_pattern() if pattern_info is None else pattern_info),
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
