import libcst as cst

from matchify.access_path import (
    AccessPath,
    AttributePathPart,
    MatchSubjectRoot,
    NameRoot,
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
