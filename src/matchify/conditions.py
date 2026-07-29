"""Boolean condition IR used before lowering predicates into match patterns."""

from __future__ import annotations

from dataclasses import dataclass, replace

import libcst as cst
from libcst import matchers as m

from .access_path import (
    AccessPath,
    AttributePathPart,
    MatchSubjectPlan,
    SubscriptPathPart,
)
from .patterns import (
    extract_isinstance_classes,
    flatten_boolean,
    is_isinstance_call,
    is_len_call,
    is_none_type_expr,
    is_qualified_value_expr,
    is_singleton_name,
    is_value_pattern_expr,
)


@dataclass(frozen=True)
class AndExpr:
    parts: tuple[BoolExpr, ...]
    original: cst.BaseExpression


@dataclass(frozen=True)
class OrExpr:
    parts: tuple[BoolExpr, ...]
    original: cst.BaseExpression


@dataclass(frozen=True)
class IsInstancePredicate:
    path: AccessPath
    classes: tuple[cst.BaseExpression, ...]
    original: cst.BaseExpression


@dataclass(frozen=True)
class LenPredicate:
    path: AccessPath
    length: int
    use_star: bool
    original: cst.BaseExpression


@dataclass(frozen=True)
class ValuePredicate:
    path: AccessPath
    value: cst.BaseExpression
    original: cst.BaseExpression
    allow_nested_pattern: bool = True


@dataclass(frozen=True)
class HasAttrPredicate:
    path: AccessPath
    attribute: str
    original: cst.BaseExpression


@dataclass(frozen=True)
class RawPredicate:
    original: cst.BaseExpression


PathPredicate = IsInstancePredicate | LenPredicate | ValuePredicate | HasAttrPredicate
Predicate = PathPredicate | RawPredicate
BoolExpr = AndExpr | OrExpr | Predicate


def parse_condition(
    condition: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
    *,
    assume_identity_equality: bool = False,
) -> BoolExpr:
    """Parse a Python condition into a logical tree with typed predicates."""
    # LibCST BooleanOperation currently only exposes And/Or operators.
    if isinstance(condition, cst.BooleanOperation):  # pragma: no branch
        if isinstance(condition.operator, cst.And):
            return AndExpr(
                tuple(
                    parse_condition(
                        part,
                        ignore_types_pattern,
                        assume_identity_equality=assume_identity_equality,
                    )
                    for part in flatten_boolean(condition, cst.And)
                ),
                condition,
            )
        if isinstance(condition.operator, cst.Or):  # pragma: no branch
            return OrExpr(
                tuple(
                    parse_condition(
                        part,
                        ignore_types_pattern,
                        assume_identity_equality=assume_identity_equality,
                    )
                    for part in flatten_boolean(condition, cst.Or)
                ),
                condition,
            )
    return parse_predicate(
        condition,
        ignore_types_pattern,
        assume_identity_equality=assume_identity_equality,
    )


def parse_predicate(
    predicate: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
    *,
    assume_identity_equality: bool = False,
) -> BoolExpr:
    if (parsed := parse_hasattr_predicate(predicate)) is not None:
        return parsed

    if is_isinstance_call(predicate):
        parsed = parse_isinstance_predicate(predicate, ignore_types_pattern)
        if parsed is not None:
            return parsed

    if isinstance(predicate, cst.Comparison) and len(predicate.comparisons) == 1:
        if (parsed := parse_membership_predicate(predicate)) is not None:
            return parsed
        if (parsed := parse_len_predicate(predicate)) is not None:
            return parsed
        if (
            parsed := parse_value_predicate(
                predicate, assume_identity_equality=assume_identity_equality
            )
        ) is not None:
            return parsed

    return RawPredicate(predicate)


def parse_hasattr_predicate(predicate: cst.BaseExpression) -> HasAttrPredicate | None:
    if not isinstance(predicate, cst.Call) or not m.matches(
        predicate, m.Call(func=m.Name(value="hasattr"), args=[m.Arg(), m.Arg()])
    ):
        return None
    name = predicate.args[1].value
    if not isinstance(name, cst.SimpleString):
        return None
    try:
        attribute = name.evaluated_value
    except ValueError:
        return None
    if not isinstance(attribute, str):
        return None
    expression = predicate.args[0].value
    return HasAttrPredicate(
        AccessPath.from_expression(expression), attribute, predicate
    )


def parse_isinstance_predicate(
    predicate: cst.Call,
    ignore_types_pattern: str | None,
) -> BoolExpr | None:
    classes = extract_isinstance_classes(predicate.args[1].value, ignore_types_pattern)
    if classes is None:
        return None
    path = AccessPath.from_expression(predicate.args[0].value)
    has_none_type, remaining_classes = split_none_type_classes(classes)
    if not has_none_type:
        return IsInstancePredicate(path, classes, predicate)

    none_predicate = value_predicate(path, cst.Name("None"), predicate)
    if not remaining_classes:
        return none_predicate
    return OrExpr(
        (
            none_predicate,
            IsInstancePredicate(path, remaining_classes, predicate),
        ),
        predicate,
    )


def split_none_type_classes(
    classes: tuple[cst.BaseExpression, ...],
) -> tuple[bool, tuple[cst.BaseExpression, ...]]:
    has_none_type = False
    remaining_classes: list[cst.BaseExpression] = []
    for class_expr in classes:
        if is_none_type_expr(class_expr):
            has_none_type = True
        else:
            remaining_classes.append(class_expr)
    return has_none_type, tuple(remaining_classes)


def parse_len_predicate(
    predicate: cst.Comparison,
) -> LenPredicate | None:
    if not is_len_call(predicate.left):
        return None
    len_call = predicate.left
    target = predicate.comparisons[0]
    if not isinstance(target.comparator, cst.Integer):
        return None
    length = int(target.comparator.value)
    use_star = len_operator_uses_star(target.operator)
    if use_star is None:
        return None
    expression = len_call.args[0].value
    return LenPredicate(
        AccessPath.from_expression(expression), length, use_star, predicate
    )


def len_operator_uses_star(operator: cst.BaseCompOp) -> bool | None:
    if isinstance(operator, cst.Equal):
        return False
    if isinstance(operator, cst.GreaterThanEqual):
        return True
    return None


def parse_membership_predicate(predicate: cst.Comparison) -> BoolExpr | None:
    target = predicate.comparisons[0]
    if not isinstance(target.operator, cst.In):
        return None
    values = extract_literal_membership_values(target.comparator)
    if values is None:
        return None
    path = AccessPath.from_expression(predicate.left)
    alternatives = tuple(value_predicate(path, value, predicate) for value in values)
    if len(alternatives) == 1:
        return alternatives[0]
    return OrExpr(alternatives, predicate)


def extract_literal_membership_values(
    container: cst.BaseExpression,
) -> tuple[cst.BaseExpression, ...] | None:
    if not isinstance(container, cst.Tuple | cst.List):
        return None
    values: list[cst.BaseExpression] = []
    for element in container.elements:
        if isinstance(element, cst.StarredElement):
            return None
        value = element.value
        if is_singleton_name(value) or not is_value_pattern_expr(value):
            return None
        values.append(value)
    return tuple(values) or None


def parse_value_predicate(
    predicate: cst.Comparison,
    *,
    assume_identity_equality: bool = False,
) -> ValuePredicate | None:
    target = predicate.comparisons[0]
    if isinstance(target.operator, cst.Equal) and is_value_pattern_expr(
        target.comparator
    ):
        return value_predicate(
            AccessPath.from_expression(predicate.left), target.comparator, predicate
        )
    if isinstance(target.operator, cst.Is) and is_singleton_name(target.comparator):
        return value_predicate(
            AccessPath.from_expression(predicate.left), target.comparator, predicate
        )
    if (
        assume_identity_equality
        and isinstance(target.operator, cst.Is)
        and is_value_pattern_expr(target.comparator)
    ):
        return value_predicate(
            AccessPath.from_expression(predicate.left), target.comparator, predicate
        )
    return None


def value_predicate(
    path: AccessPath,
    value: cst.BaseExpression,
    original: cst.BaseExpression,
) -> ValuePredicate:
    return ValuePredicate(
        path,
        value,
        original,
        allow_nested_pattern=not is_qualified_value_expr(value),
    )


def select_subject_path(expr: BoolExpr) -> AccessPath | None:
    """Select a match-subject candidate from unbound condition IR."""
    if isinstance(expr, OrExpr):
        paths = tuple(select_subject_path(part) for part in expr.parts)
        first = paths[0]
        if first is None or any(path != first for path in paths[1:]):
            return None
        return first
    if isinstance(expr, AndExpr):
        subject = find_isinstance_subject_path(expr, include_subscripts=False)
        if subject is not None:
            return subject
        subject = find_sequence_subject_path(expr)
        if subject is not None:
            return subject
        subject = find_value_subject_path(expr)
        if subject is not None:
            return subject
        return find_isinstance_subject_path(expr, include_subscripts=True)
    if isinstance(expr, IsInstancePredicate):
        return expr.path
    if isinstance(expr, ValuePredicate):
        return expr.path
    return None


def select_subject_paths(expr: BoolExpr) -> tuple[AccessPath, ...] | None:
    """Select the conservatively evaluated subject from condition IR."""
    subject = select_subject_path(expr)
    return None if subject is None else (subject,)


def select_assumed_pure_subject_paths(expr: BoolExpr) -> tuple[AccessPath, ...] | None:
    """Select every independent subject when eager evaluation is permitted."""
    primary = select_subject_path(expr)
    if primary is None:
        return None
    subjects = [primary]
    if isinstance(expr, AndExpr):
        for part in expr.parts:
            candidates = select_subject_paths(part)
            if candidates is None:
                continue
            for candidate in candidates:
                merge_subject_candidate(subjects, candidate)
    return tuple(subjects)


def merge_subject_candidate(subjects: list[AccessPath], candidate: AccessPath) -> None:
    for index, subject in enumerate(subjects):
        if candidate.starts_with(subject):
            return
        if subject.starts_with(candidate):
            subjects[index] = candidate
            return
    subjects.append(candidate)


def find_isinstance_subject_path(
    expr: BoolExpr, *, include_subscripts: bool
) -> AccessPath | None:
    for part in iter_and_parts(expr):
        if isinstance(part, IsInstancePredicate):
            if include_subscripts or not part.path.contains_subscript:
                return part.path
    return None


def find_sequence_subject_path(expr: BoolExpr) -> AccessPath | None:
    parts = tuple(iter_and_parts(expr))
    for part in parts:
        if not isinstance(part, LenPredicate):
            continue
        if any(has_direct_sequence_element_check(other, part.path) for other in parts):
            return part.path
    return None


def has_direct_sequence_element_check(expr: BoolExpr, subject: AccessPath) -> bool:
    if isinstance(expr, AndExpr):
        return any(
            has_direct_sequence_element_check(part, subject) for part in expr.parts
        )
    if isinstance(expr, OrExpr):
        return all(
            has_direct_sequence_element_check(part, subject) for part in expr.parts
        )
    if isinstance(expr, PathPredicate):
        path = expr.path
    else:
        return False
    return isinstance(path.first_part_after(subject), SubscriptPathPart)


def find_value_subject_path(expr: BoolExpr) -> AccessPath | None:
    for part in iter_and_parts(expr):
        if isinstance(part, OrExpr):
            subject = select_subject_path(part)
            if subject is not None and not subject.contains_subscript:
                return subject
            continue
        if isinstance(part, ValuePredicate) and not part.path.contains_subscript:
            return part.path
    return None


def iter_and_parts(expr: BoolExpr) -> tuple[BoolExpr, ...]:
    if isinstance(expr, AndExpr):
        return expr.parts
    return (expr,)


def bind_condition_subject(expr: BoolExpr, subject: MatchSubjectPlan) -> BoolExpr:
    """Bind unbound predicate expressions to paths relative to the match subject."""
    if isinstance(expr, AndExpr):
        return AndExpr(
            tuple(bind_condition_subject(part, subject) for part in expr.parts),
            expr.original,
        )
    if isinstance(expr, OrExpr):
        return OrExpr(
            tuple(bind_condition_subject(part, subject) for part in expr.parts),
            expr.original,
        )
    return bind_predicate_subject(expr, subject)


def remove_implied_checks(expr: BoolExpr) -> BoolExpr:
    """Remove conditions already enforced by a structural pattern."""
    if isinstance(expr, OrExpr):
        return OrExpr(
            tuple(remove_implied_checks(part) for part in expr.parts),
            expr.original,
        )
    if not isinstance(expr, AndExpr):
        return expr

    parts = tuple(remove_implied_checks(part) for part in expr.parts)
    checked_paths = {path for part in parts for path in checked_pattern_paths(part)}
    return AndExpr(
        tuple(
            part
            for part in parts
            if not hasattr_predicate_is_implied(part, checked_paths)
        ),
        expr.original,
    )


def hasattr_predicate_is_implied(
    expr: BoolExpr,
    checked_paths: set[AccessPath],
) -> bool:
    return bool(
        isinstance(expr, HasAttrPredicate)
        and expr.path.is_bound
        and any(
            path == expr.path or path.starts_with(expr.path) for path in checked_paths
        )
    )


def checked_pattern_paths(expr: BoolExpr) -> set[AccessPath]:
    if isinstance(expr, AndExpr):
        return set().union(*(checked_pattern_paths(part) for part in expr.parts))
    if isinstance(expr, OrExpr):
        paths = [checked_pattern_paths(part) for part in expr.parts]
        merged = set().union(*paths)
        return merged if len(merged) == 1 else set()
    if isinstance(expr, IsInstancePredicate):
        return {expr.path} if expr.path.is_bound else set()
    if isinstance(expr, LenPredicate):
        return {expr.path} if expr.path.is_bound else set()
    if not isinstance(expr, ValuePredicate) or not expr.path.is_bound:
        return set()
    return (
        {expr.path}
        if expr.path.parts and isinstance(expr.path.parts[-1], AttributePathPart)
        else set()
    )


def bind_predicate_subject(
    predicate: Predicate, subject: MatchSubjectPlan
) -> Predicate:
    if isinstance(predicate, RawPredicate):
        return predicate

    path = predicate.path
    if isinstance(predicate, HasAttrPredicate):
        path = AccessPath(
            path.root, (*path.parts, AttributePathPart(predicate.attribute))
        )
    path = subject.bind(path)
    return replace(predicate, path=path)


def residual_condition(expr: BoolExpr | None) -> cst.BaseExpression | None:
    """Render remaining BoolExpr nodes back to their original condition shape."""
    if expr is None:
        return None
    if isinstance(expr, AndExpr):
        rendered = [
            condition for part in expr.parts if (condition := residual_condition(part))
        ]
        if not rendered:
            return None
        if len(rendered) == 1:
            return rendered[0]
        expression = rendered[0]
        for condition in rendered[1:]:
            expression = cst.BooleanOperation(
                left=expression,
                operator=cst.And(),
                right=condition,
            )
        return expression
    if isinstance(expr, OrExpr):
        return expr.original
    return expr.original
