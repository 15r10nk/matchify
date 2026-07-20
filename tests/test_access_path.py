import libcst as cst
import pytest

from matchify.access_path import (
    AccessPath,
    AttributePathPart,
    MatchSubjectPlan,
    MatchSubjectRoot,
    NameRoot,
    SubscriptPathPart,
)


def parse_expression(source: str) -> cst.BaseExpression:
    return cst.parse_expression(source)


def test_binding_replaces_a_multi_part_subject_prefix():
    path = AccessPath.from_expression(parse_expression("self.node.value"))
    subject = AccessPath.from_expression(parse_expression("self.node"))

    assert path.bind(subject) == AccessPath(
        MatchSubjectRoot(), (AttributePathPart("value"),)
    )


def test_binding_preserves_a_path_outside_the_subject():
    path = AccessPath.from_expression(parse_expression("config.enabled"))
    subject = AccessPath.from_expression(parse_expression("self.node"))

    assert path.bind(subject) == AccessPath(
        NameRoot("config"), (AttributePathPart("enabled"),)
    )


def test_binding_can_target_a_synthetic_tuple_slot():
    path = AccessPath.from_expression(parse_expression("node.value"))
    subject = AccessPath.from_expression(parse_expression("node"))

    assert path.bind(subject, (SubscriptPathPart(1),)) == AccessPath(
        MatchSubjectRoot(),
        (SubscriptPathPart(1), AttributePathPart("value")),
    )


def test_dynamic_subscript_paths_preserve_their_expression_identity():
    left = AccessPath.from_expression(parse_expression("items[i]"))
    right = AccessPath.from_expression(parse_expression("items[j]"))
    sliced = AccessPath.from_expression(parse_expression("items[0:1]"))

    assert left != right
    assert left != sliced
    assert right != sliced


def test_common_prefix_can_be_rendered_as_fresh_cst():
    left = AccessPath.from_expression(parse_expression("node.left.value"))
    right = AccessPath.from_expression(parse_expression("node.left.kind"))

    prefix = AccessPath.common_prefix((left, right))

    assert prefix is not None
    assert cst.Module([]).code_for_node(prefix.to_expression()) == "node.left"


def test_dynamic_subscript_subject_can_be_rendered_as_fresh_cst():
    path = AccessPath.from_expression(parse_expression("items[index]"))

    assert cst.Module([]).code_for_node(path.to_expression()) == "items[index]"


def test_subject_plan_binds_multiple_subjects_to_tuple_slots():
    first = AccessPath.from_expression(parse_expression("a.x"))
    second = AccessPath.from_expression(parse_expression("b.y"))
    plan = MatchSubjectPlan.from_subjects((first, second))

    first_child = AccessPath.from_expression(parse_expression("a.x.value"))
    second_child = AccessPath.from_expression(parse_expression("b.y.kind"))

    assert plan.bind(first_child) == AccessPath(
        MatchSubjectRoot(),
        (SubscriptPathPart(0), AttributePathPart("value")),
    )
    assert plan.bind(second_child) == AccessPath(
        MatchSubjectRoot(),
        (SubscriptPathPart(1), AttributePathPart("kind")),
    )
    assert cst.Module([]).code_for_node(plan.to_expression()) == "(a.x, b.y)"


def test_subject_plan_rejects_overlapping_subjects():
    parent = AccessPath.from_expression(parse_expression("node"))
    child = AccessPath.from_expression(parse_expression("node.value"))

    with pytest.raises(ValueError, match="must not overlap"):
        MatchSubjectPlan.from_subjects((parent, child))
