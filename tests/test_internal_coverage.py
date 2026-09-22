from textwrap import dedent

import libcst as cst

from matchify.access_path import AccessPath, MatchSubjectRoot, NameRoot
from matchify.assumptions import Assumptions
from matchify.conditions import (
    IsInstancePredicate,
    OrExpr,
    RawPredicate,
    parse_condition,
)
from matchify.facts import WildcardNode
from matchify.lookup_tables import compile_local_lookups
from matchify.pattern_builder import assumes_sequence_type_check, is_sequence_type_check


def test_wildcard_node_renders_a_match_wildcard():
    pattern = WildcardNode().render()

    assert isinstance(pattern, cst.MatchAs)
    assert pattern.pattern is None
    assert pattern.name is None


def test_sequence_type_check_rejects_non_isinstance_exprs():
    expr = RawPredicate(cst.Name("flag"))

    assert not is_sequence_type_check(expr)
    assert not assumes_sequence_type_check(expr, Assumptions.safe())


def test_sequence_type_check_accepts_list_and_tuple_isinstance_predicates():
    expr = IsInstancePredicate(
        path=AccessPath(NameRoot("value")),
        classes=(cst.Name("list"), cst.Name("tuple")),
        original=cst.Name("condition"),
    )

    assert is_sequence_type_check(expr)
    assert assumes_sequence_type_check(
        expr,
        Assumptions.LIST_SEQUENCE_PATTERN | Assumptions.TUPLE_SEQUENCE_PATTERN,
    )


def test_sequence_type_check_rejects_non_sequence_class_names():
    expr = IsInstancePredicate(
        path=AccessPath(MatchSubjectRoot()),
        classes=(cst.Name("CustomSequence"),),
        original=cst.Name("condition"),
    )

    assert not is_sequence_type_check(expr)


def test_safe_condition_parser_keeps_set_membership_in_a_guard():
    condition = cst.parse_expression("value in {1, 2}")

    parsed = parse_condition(condition, None, assumptions=Assumptions.safe())
    assert isinstance(parsed, RawPredicate)
    assert parsed.original.deep_equals(condition)
    assert isinstance(
        parse_condition(condition, None, assumptions=Assumptions.HASHABLE_SUBJECTS),
        OrExpr,
    )


def test_local_lookup_analysis_without_rewriting():
    module = cst.parse_module(
        dedent(
            """\
            def choose(key):
                table = {"a": 1, "b": 2}
                return table[key]
            """
        )
    )
    function = module.body[0]
    assert isinstance(function, cst.FunctionDef)
    assert isinstance(function.body, cst.IndentedBlock)

    body, required = compile_local_lookups(function.body, enabled=False)

    assert body.deep_equals(function.body)
    assert required == (function.body.body[0],)
