import libcst as cst

from matchify.access_path import AccessPath, MatchSubjectRoot, NameRoot
from matchify.assumptions import Assumptions
from matchify.conditions import IsInstancePredicate, RawPredicate
from matchify.facts import WildcardNode
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
