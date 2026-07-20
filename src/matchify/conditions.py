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
    is_list_tuple_classes,
    is_literal_value,
    is_singleton_name,
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
class ProductExpr:
    """Predicates from one eagerly evaluated tuple comparison."""

    parts: tuple[Predicate, ...]
    original: cst.BaseExpression


@dataclass(frozen=True)
class IsInstancePredicate:
    path: AccessPath
    classes: tuple[cst.BaseExpression, ...]
    original: cst.BaseExpression


@dataclass(frozen=True)
class LenEqualsPredicate:
    path: AccessPath
    length: int
    original: cst.BaseExpression


@dataclass(frozen=True)
class LenAtLeastPredicate:
    path: AccessPath
    minimum: int
    original: cst.BaseExpression


@dataclass(frozen=True)
class SequenceTypePredicate:
    path: AccessPath
    original: cst.BaseExpression


@dataclass(frozen=True)
class EqualsPredicate:
    path: AccessPath
    value: cst.BaseExpression
    original: cst.BaseExpression


@dataclass(frozen=True)
class IsPredicate:
    path: AccessPath
    value: cst.BaseExpression
    original: cst.BaseExpression


@dataclass(frozen=True)
class HasAttrPredicate:
    path: AccessPath
    attribute: str
    original: cst.BaseExpression


@dataclass(frozen=True)
class RawPredicate:
    original: cst.BaseExpression


Predicate = (
    IsInstancePredicate
    | LenEqualsPredicate
    | LenAtLeastPredicate
    | SequenceTypePredicate
    | EqualsPredicate
    | IsPredicate
    | HasAttrPredicate
    | RawPredicate
)
BoolExpr = AndExpr | OrExpr | ProductExpr | Predicate


def parse_condition(
    condition: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
) -> BoolExpr:
    """Parse a Python condition into a logical tree with typed predicates."""
    # LibCST BooleanOperation currently only exposes And/Or operators.
    if isinstance(condition, cst.BooleanOperation):  # pragma: no branch
        if isinstance(condition.operator, cst.And):
            return AndExpr(
                tuple(
                    parse_condition(part, ignore_types_pattern)
                    for part in flatten_boolean(condition, cst.And)
                ),
                condition,
            )
        if isinstance(condition.operator, cst.Or):  # pragma: no branch
            return OrExpr(
                tuple(
                    parse_condition(part, ignore_types_pattern)
                    for part in flatten_boolean(condition, cst.Or)
                ),
                condition,
            )
    return parse_predicate(condition, ignore_types_pattern)


def parse_predicate(
    predicate: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
) -> Predicate:
    if (parsed := parse_hasattr_predicate(predicate)) is not None:
        return parsed

    if is_isinstance_call(predicate):
        parsed = parse_isinstance_predicate(predicate, ignore_types_pattern)
        if parsed is not None:
            return parsed

    if isinstance(predicate, cst.Comparison) and len(predicate.comparisons) == 1:
        if (parsed := parse_product_predicate(predicate)) is not None:
            return parsed
        if (parsed := parse_len_predicate(predicate)) is not None:
            return parsed
        if (parsed := parse_value_predicate(predicate)) is not None:
            return parsed

    return RawPredicate(predicate)


def parse_product_predicate(predicate: cst.Comparison) -> ProductExpr | None:
    target = predicate.comparisons[0]
    if (
        not isinstance(target.operator, cst.Equal)
        or not isinstance(predicate.left, cst.Tuple)
        or not isinstance(target.comparator, cst.Tuple)
        or len(predicate.left.elements) != len(target.comparator.elements)
        or not predicate.left.elements
    ):
        return None

    predicates = []
    for left_element, right_element in zip(
        predicate.left.elements, target.comparator.elements
    ):
        if (
            isinstance(left_element, cst.StarredElement)
            or isinstance(right_element, cst.StarredElement)
            or not is_literal_value(right_element.value)
        ):
            return None
        original = cst.Comparison(
            left=left_element.value,
            comparisons=[
                cst.ComparisonTarget(
                    operator=cst.Equal(), comparator=right_element.value
                )
            ],
        )
        predicates.append(
            EqualsPredicate(
                AccessPath.from_expression(left_element.value),
                right_element.value,
                original,
            )
        )
    return ProductExpr(tuple(predicates), predicate)


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
) -> IsInstancePredicate | SequenceTypePredicate | None:
    classes = extract_isinstance_classes(predicate.args[1].value, ignore_types_pattern)
    if classes is None:
        return None
    if is_list_tuple_classes(classes):
        expression = predicate.args[0].value
        return SequenceTypePredicate(AccessPath.from_expression(expression), predicate)
    expression = predicate.args[0].value
    return IsInstancePredicate(
        AccessPath.from_expression(expression), classes, predicate
    )


def parse_len_predicate(
    predicate: cst.Comparison,
) -> LenEqualsPredicate | LenAtLeastPredicate | None:
    if not is_len_call(predicate.left):
        return None
    len_call = predicate.left
    target = predicate.comparisons[0]
    if not isinstance(target.comparator, cst.Integer):
        return None
    length = int(target.comparator.value)
    if isinstance(target.operator, cst.Equal):
        expression = len_call.args[0].value
        return LenEqualsPredicate(
            AccessPath.from_expression(expression), length, predicate
        )
    if isinstance(target.operator, cst.GreaterThanEqual):
        expression = len_call.args[0].value
        return LenAtLeastPredicate(
            AccessPath.from_expression(expression), length, predicate
        )
    return None


def parse_value_predicate(
    predicate: cst.Comparison,
) -> EqualsPredicate | IsPredicate | None:
    target = predicate.comparisons[0]
    if isinstance(target.operator, cst.Equal) and is_literal_value(target.comparator):
        return EqualsPredicate(
            AccessPath.from_expression(predicate.left), target.comparator, predicate
        )
    if isinstance(target.operator, cst.Is) and is_singleton_name(target.comparator):
        return IsPredicate(
            AccessPath.from_expression(predicate.left), target.comparator, predicate
        )
    return None


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
    if isinstance(expr, EqualsPredicate | IsPredicate):
        return expr.path
    return None


def select_subject_paths(expr: BoolExpr) -> tuple[AccessPath, ...] | None:
    """Select one or more eagerly evaluated subjects from condition IR."""
    if isinstance(expr, ProductExpr):
        return tuple(part.path for part in expr.parts)
    subject = select_subject_path(expr)
    return None if subject is None else (subject,)


def find_isinstance_subject_path(
    expr: BoolExpr, *, include_subscripts: bool
) -> AccessPath | None:
    for part in iter_and_parts(expr):
        if isinstance(part, IsInstancePredicate):
            if include_subscripts or not path_contains_subscript(part.path):
                return part.path
    return None


def find_sequence_subject_path(expr: BoolExpr) -> AccessPath | None:
    parts = tuple(iter_and_parts(expr))
    for part in parts:
        if not isinstance(part, LenEqualsPredicate | LenAtLeastPredicate):
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
    if isinstance(
        expr,
        (
            EqualsPredicate,
            IsPredicate,
            IsInstancePredicate,
            LenEqualsPredicate,
            LenAtLeastPredicate,
            SequenceTypePredicate,
        ),
    ):
        path = expr.path
    elif isinstance(expr, RawPredicate):
        path = raw_predicate_access_path(expr)
    else:
        return False
    if path is None or not path.starts_with(subject) or path == subject:
        return False
    return isinstance(path.parts[len(subject.parts)], SubscriptPathPart)


def raw_predicate_access_path(predicate: RawPredicate) -> AccessPath | None:
    node = predicate.original
    if is_isinstance_call(node):
        return AccessPath.from_expression(node.args[0].value)
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    if is_len_call(node.left):
        return AccessPath.from_expression(node.left.args[0].value)
    return AccessPath.from_expression(node.left)


def find_value_subject_path(expr: BoolExpr) -> AccessPath | None:
    for part in iter_and_parts(expr):
        if isinstance(part, OrExpr):
            subject = select_subject_path(part)
            if subject is not None and not path_contains_subscript(subject):
                return subject
            continue
        if isinstance(
            part, EqualsPredicate | IsPredicate
        ) and not path_contains_subscript(part.path):
            return part.path
    return None


def path_contains_subscript(path: AccessPath) -> bool:
    return any(isinstance(part, SubscriptPathPart) for part in path.parts)


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
    if isinstance(expr, ProductExpr):
        return ProductExpr(
            tuple(bind_predicate_subject(part, subject) for part in expr.parts),
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
    if isinstance(expr, ProductExpr):
        return ProductExpr(
            tuple(
                part
                for part in expr.parts
                if not condition_is_implied(
                    part,
                    {
                        path
                        for candidate in expr.parts
                        for path in checked_pattern_paths(candidate)
                    },
                )
            ),
            expr.original,
        )
    if not isinstance(expr, AndExpr):
        return expr

    parts = tuple(remove_implied_checks(part) for part in expr.parts)
    checked_paths = {path for part in parts for path in checked_pattern_paths(part)}
    return AndExpr(
        tuple(part for part in parts if not condition_is_implied(part, checked_paths)),
        expr.original,
    )


def condition_is_implied(
    expr: BoolExpr,
    checked_paths: set[AccessPath],
) -> bool:
    if isinstance(expr, HasAttrPredicate) and expr.path.is_bound:
        return any(
            path == expr.path or path.starts_with(expr.path) for path in checked_paths
        )
    return bool(
        isinstance(expr, SequenceTypePredicate)
        and expr.path.is_subject
        and expr.path in checked_paths
    )


def checked_pattern_paths(expr: BoolExpr) -> set[AccessPath]:
    if isinstance(expr, AndExpr | ProductExpr):
        return set().union(*(checked_pattern_paths(part) for part in expr.parts))
    if isinstance(expr, OrExpr):
        paths = [checked_pattern_paths(part) for part in expr.parts]
        merged = set().union(*paths)
        return merged if len(merged) == 1 else set()
    if isinstance(expr, IsInstancePredicate):
        return {expr.path} if expr.path.is_bound else set()
    if isinstance(expr, LenEqualsPredicate | LenAtLeastPredicate):
        return {expr.path} if expr.path.is_bound else set()
    if not isinstance(expr, EqualsPredicate | IsPredicate) or not expr.path.is_bound:
        return set()
    return (
        {expr.path}
        if expr.path and isinstance(expr.path.parts[-1], AttributePathPart)
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
    if not path.is_bound or has_unknown_subscript(path):
        return replace(predicate, path=path)

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
    if isinstance(expr, ProductExpr):
        return expr.original
    return expr.original


def has_unknown_subscript(path: AccessPath) -> bool:
    """Return true when a path contains a subscript that cannot become a pattern index."""
    return any(
        isinstance(part, SubscriptPathPart) and part.index is None
        for part in path.parts
    )
