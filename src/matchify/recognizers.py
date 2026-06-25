"""Recognizers that turn branch conditions into match patterns and guards."""

import libcst as cst
from libcst import matchers as m

from .facts import BranchFacts
from .pattern_builder import normalize_with_bool_tree
from .patterns import (
    extract_isinstance_classes,
    flatten_boolean,
    is_isinstance_call,
    is_len_call,
    is_list_tuple_classes,
    is_literal_value,
    is_singleton_name,
)
from .subject_path import AttributePathPart, SubjectPath


def remove_redundant_subject_checks(
    part: cst.BaseExpression,
    subject: cst.BaseExpression,
) -> cst.BaseExpression:
    if not isinstance(part, cst.BooleanOperation) or not isinstance(
        part.operator, cst.And
    ):
        return part

    components = flatten_boolean(part, cst.And)
    checked_paths = {
        path
        for component in components
        for path in collect_checked_attribute_paths(component, subject)
    }
    if not checked_paths:
        return part

    filtered = [
        component
        for component in components
        if not is_redundant_hasattr(component, subject, checked_paths)
        and not should_remove_redundant_sequence_type_check(
            component, subject, checked_paths
        )
    ]
    if len(filtered) == len(components):
        return part
    # If pruning leaves one condition we return it directly; otherwise rebuild AND.
    if len(filtered) == 1:  # pragma: no branch
        return filtered[0]
    expression = filtered[0]
    for component in filtered[1:]:
        expression = cst.BooleanOperation(
            left=expression,
            operator=cst.And(),
            right=component,
        )
    return expression


def is_redundant_hasattr(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
) -> bool:
    hasattr_path = extract_hasattr_attribute_path(node, subject)
    return hasattr_path is not None and any(
        path == hasattr_path or path.starts_with(hasattr_path) for path in checked_paths
    )


def should_remove_redundant_sequence_type_check(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
) -> bool:
    sequence_path = extract_list_tuple_isinstance_path(node, subject)
    return (
        sequence_path is not None
        and sequence_path in checked_paths
        and sequence_path.is_subject
    )


def extract_list_tuple_isinstance_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not is_isinstance_call(node):
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:
        return None
    classes = extract_isinstance_classes(node.args[1].value, ignore_types_pattern=None)
    if classes is None or not is_list_tuple_classes(classes):
        return None
    return path


def collect_checked_attribute_paths(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> set[SubjectPath]:
    if isinstance(node, cst.BooleanOperation) and isinstance(node.operator, cst.Or):
        parts = [
            collect_checked_attribute_paths(part, subject)
            for part in flatten_boolean(node, cst.Or)
        ]
        merged = set().union(*parts)
        return merged if len(merged) == 1 else set()

    if is_isinstance_call(node):
        path = SubjectPath.from_expression(node.args[0].value, subject)
        if path is None or not path:
            return set()
        return {path}

    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return set()

    if is_len_call(node.left):
        len_call = node.left
        path = SubjectPath.from_expression(len_call.args[0].value, subject)
        if path is None:
            return set()
        return {path}

    path = SubjectPath.from_expression(node.left, subject)
    if path is None or not path or not isinstance(path.parts[-1], AttributePathPart):
        return set()

    target = node.comparisons[0]
    if isinstance(  # pragma: no branch
        target.operator, cst.Is
    ) and not is_singleton_name(target.comparator):
        return set()
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return set()
    # Non-literal attribute comparisons are kept as guards by the builder.
    if not is_literal_value(target.comparator):  # pragma: no branch
        return set()

    return {path}


def extract_hasattr_attribute_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"), args=[m.Arg(), m.Arg()])
    ):
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:  # pragma: no cover
        return None
    name_arg = node.args[1].value
    if not isinstance(name_arg, cst.SimpleString):  # pragma: no cover
        return None
    try:
        value = cst.ensure_type(cst.parse_expression(name_arg.value), cst.SimpleString)
    except cst.ParserSyntaxError:  # pragma: no cover
        return None
    literal = value.evaluated_value
    if not isinstance(literal, str):  # pragma: no cover
        return None
    return SubjectPath((*path.parts, AttributePathPart(literal)))


def normalize_branch(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
) -> BranchFacts:
    bool_tree_condition = prepare_bool_tree_condition(
        condition,
        subject,
    )
    bool_tree_branch = normalize_with_bool_tree(
        bool_tree_condition, subject, ignore_types_pattern
    )
    # Normal public conversions use the BoolExpr path; fallback remains for
    # unsupported future predicates.
    if bool_tree_branch is not None:  # pragma: no branch
        return bool_tree_branch

    return BranchFacts(
        pattern=None,
        guard=condition,
    )


def prepare_bool_tree_condition(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
) -> cst.BaseExpression:
    if isinstance(condition, cst.BooleanOperation) and isinstance(
        condition.operator, (cst.And, cst.Or)
    ):
        operator_type = cst.And if isinstance(condition.operator, cst.And) else cst.Or
        parts = [
            prepare_bool_tree_condition(part, subject)
            for part in flatten_boolean(condition, operator_type)
        ]
        expression = parts[0]
        for part in parts[1:]:
            expression = cst.BooleanOperation(
                left=expression,
                operator=operator_type(),
                right=part,
            )
        expression = expression.with_changes(
            lpar=condition.lpar,
            rpar=condition.rpar,
        )
        return remove_redundant_subject_checks(
            expression,
            subject,
        )

    return remove_redundant_subject_checks(
        condition,
        subject,
    )
