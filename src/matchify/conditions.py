"""Boolean condition IR used before lowering predicates into match patterns."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

import libcst as cst
from libcst import matchers as m

from .patterns import (
    extract_isinstance_classes,
    flatten_boolean,
    is_isinstance_call,
    is_len_call,
    is_list_tuple_classes,
    is_literal_value,
    is_singleton_name,
)
from .subject_path import AttributePathPart, SubjectPath, SubscriptPathPart


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
    expression: cst.BaseExpression
    classes: tuple[cst.BaseExpression, ...]
    original: cst.BaseExpression
    path: SubjectPath | None = None


@dataclass(frozen=True)
class LenEqualsPredicate:
    expression: cst.BaseExpression
    length: int
    original: cst.BaseExpression
    path: SubjectPath | None = None


@dataclass(frozen=True)
class LenAtLeastPredicate:
    expression: cst.BaseExpression
    minimum: int
    original: cst.BaseExpression
    path: SubjectPath | None = None


@dataclass(frozen=True)
class SequenceTypePredicate:
    expression: cst.BaseExpression
    original: cst.BaseExpression
    path: SubjectPath | None = None


@dataclass(frozen=True)
class EqualsPredicate:
    expression: cst.BaseExpression
    value: cst.BaseExpression
    original: cst.BaseExpression
    path: SubjectPath | None = None


@dataclass(frozen=True)
class IsPredicate:
    expression: cst.BaseExpression
    value: cst.BaseExpression
    original: cst.BaseExpression
    path: SubjectPath | None = None


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
    | RawPredicate
)
BoolExpr = AndExpr | OrExpr | Predicate


def contains_subscript(node: cst.CSTNode) -> bool:
    return bool(m.findall(node, m.Subscript()))


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
    if is_isinstance_call(predicate):
        parsed = parse_isinstance_predicate(predicate, ignore_types_pattern)
        if parsed is not None:
            return parsed

    if isinstance(predicate, cst.Comparison) and len(predicate.comparisons) == 1:
        if (parsed := parse_len_predicate(predicate)) is not None:
            return parsed
        if (parsed := parse_value_predicate(predicate)) is not None:
            return parsed

    return RawPredicate(predicate)


def parse_isinstance_predicate(
    predicate: cst.Call,
    ignore_types_pattern: str | None,
) -> IsInstancePredicate | SequenceTypePredicate | None:
    classes = extract_isinstance_classes(predicate.args[1].value, ignore_types_pattern)
    if classes is None:
        return None
    if is_list_tuple_classes(classes):
        return SequenceTypePredicate(predicate.args[0].value, predicate)
    return IsInstancePredicate(predicate.args[0].value, classes, predicate)


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
        return LenEqualsPredicate(len_call.args[0].value, length, predicate)
    if isinstance(target.operator, cst.GreaterThanEqual):
        return LenAtLeastPredicate(len_call.args[0].value, length, predicate)
    return None


def parse_value_predicate(
    predicate: cst.Comparison,
) -> EqualsPredicate | IsPredicate | None:
    target = predicate.comparisons[0]
    if isinstance(target.operator, cst.Equal) and is_literal_value(target.comparator):
        return EqualsPredicate(predicate.left, target.comparator, predicate)
    if isinstance(target.operator, cst.Is) and is_singleton_name(target.comparator):
        return IsPredicate(predicate.left, target.comparator, predicate)
    return None


def infer_subject(expr: BoolExpr) -> cst.BaseExpression | None:
    """Infer the common match subject from an unbound BoolExpr tree."""
    if isinstance(expr, OrExpr):
        return common_subject(infer_subject(part) for part in expr.parts)
    if isinstance(expr, AndExpr):
        subject = find_isinstance_subject(expr, include_subscripts=False)
        if subject is not None:
            return subject
        subject = find_sequence_subject(expr)
        if subject is not None:
            return subject
        subject = find_value_subject(expr)
        if subject is not None:
            return subject
        return find_isinstance_subject(expr, include_subscripts=True)
    if isinstance(expr, IsInstancePredicate):
        return expr.expression
    if isinstance(expr, EqualsPredicate | IsPredicate):
        return expr.expression
    return None


def common_subject(
    subjects: Iterable[cst.BaseExpression | None],
) -> cst.BaseExpression | None:
    subject: cst.BaseExpression | None = None
    for candidate in subjects:
        if not isinstance(candidate, cst.BaseExpression):
            return None
        if subject is None:
            subject = candidate
        elif not candidate.deep_equals(subject):
            return None
    return subject


def find_isinstance_subject(
    expr: BoolExpr, *, include_subscripts: bool
) -> cst.BaseExpression | None:
    for part in iter_and_parts(expr):
        if isinstance(part, IsInstancePredicate):
            if include_subscripts or not contains_subscript(part.expression):
                return part.expression
    return None


def find_sequence_subject(expr: BoolExpr) -> cst.BaseExpression | None:
    parts = tuple(iter_and_parts(expr))
    for part in parts:
        if not isinstance(part, LenEqualsPredicate | LenAtLeastPredicate):
            continue
        if any(
            has_direct_sequence_element_check(other, part.expression) for other in parts
        ):
            return part.expression
    return None


def has_direct_sequence_element_check(
    expr: BoolExpr, subject: cst.BaseExpression
) -> bool:
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
        path = SubjectPath.from_expression(expr.expression, subject)
        return path is not None and path.starts_with_subscript
    if isinstance(expr, RawPredicate):
        path = raw_predicate_subject_path(expr, subject)
        return path is not None and path.starts_with_subscript
    return False


def raw_predicate_subject_path(
    predicate: RawPredicate, subject: cst.BaseExpression
) -> SubjectPath | None:
    node = predicate.original
    if is_isinstance_call(node):
        return SubjectPath.from_expression(node.args[0].value, subject)
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    if is_len_call(node.left):
        return SubjectPath.from_expression(node.left.args[0].value, subject)
    return SubjectPath.from_expression(node.left, subject)


def find_value_subject(expr: BoolExpr) -> cst.BaseExpression | None:
    for part in iter_and_parts(expr):
        if isinstance(part, OrExpr):
            subject = infer_subject(part)
            if subject is not None and not contains_subscript(subject):
                return subject
            continue
        if isinstance(part, EqualsPredicate | IsPredicate) and not contains_subscript(
            part.expression
        ):
            return part.expression
    return None


def iter_and_parts(expr: BoolExpr) -> tuple[BoolExpr, ...]:
    if isinstance(expr, AndExpr):
        return expr.parts
    return (expr,)


def bind_condition_subject(expr: BoolExpr, subject: cst.BaseExpression) -> BoolExpr:
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


def remove_implied_checks(expr: BoolExpr, subject: cst.BaseExpression) -> BoolExpr:
    """Remove conditions already enforced by a structural pattern."""
    if isinstance(expr, OrExpr):
        return OrExpr(
            tuple(remove_implied_checks(part, subject) for part in expr.parts),
            expr.original,
        )
    if not isinstance(expr, AndExpr):
        return expr

    parts = tuple(remove_implied_checks(part, subject) for part in expr.parts)
    checked_paths = {
        path
        for part in parts
        for path in checked_attribute_paths(part.original, subject)
    }
    return AndExpr(
        tuple(
            part
            for part in parts
            if not condition_is_implied(part.original, subject, checked_paths)
        ),
        expr.original,
    )


def condition_is_implied(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
) -> bool:
    hasattr_path = hasattr_attribute_path(node, subject)
    if hasattr_path is not None:
        return any(
            path == hasattr_path or path.starts_with(hasattr_path)
            for path in checked_paths
        )

    sequence_path = list_tuple_isinstance_path(node, subject)
    return (
        sequence_path is not None
        and sequence_path.is_subject
        and sequence_path in checked_paths
    )


def list_tuple_isinstance_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not is_isinstance_call(node):
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    classes = extract_isinstance_classes(node.args[1].value, ignore_types_pattern=None)
    return path if classes is not None and is_list_tuple_classes(classes) else None


def checked_attribute_paths(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> set[SubjectPath]:
    if isinstance(node, cst.BooleanOperation) and isinstance(node.operator, cst.Or):
        paths = [
            checked_attribute_paths(part, subject)
            for part in flatten_boolean(node, cst.Or)
        ]
        merged = set().union(*paths)
        return merged if len(merged) == 1 else set()

    if is_isinstance_call(node):
        path = SubjectPath.from_expression(node.args[0].value, subject)
        return {path} if path else set()

    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return set()
    if is_len_call(node.left):
        path = SubjectPath.from_expression(node.left.args[0].value, subject)
        return {path} if path is not None else set()

    path = SubjectPath.from_expression(node.left, subject)
    if path is None or not path or not isinstance(path.parts[-1], AttributePathPart):
        return set()
    target = node.comparisons[0]
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return set()
    if isinstance(target.operator, cst.Is) and not is_singleton_name(target.comparator):
        return set()
    return {path} if is_literal_value(target.comparator) else set()


def hasattr_attribute_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"), args=[m.Arg(), m.Arg()])
    ):
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    name_arg = node.args[1].value
    if path is None or not isinstance(name_arg, cst.SimpleString):
        return None
    try:
        name = name_arg.evaluated_value
    except ValueError:
        return None
    if not isinstance(name, str):
        return None
    return SubjectPath((*path.parts, AttributePathPart(name)))


def bind_predicate_subject(
    predicate: Predicate, subject: cst.BaseExpression
) -> Predicate:
    if isinstance(predicate, RawPredicate):
        return predicate

    path = SubjectPath.from_expression(predicate.expression, subject)
    if path is None or has_unknown_subscript(path):
        return RawPredicate(predicate.original)

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


def has_unknown_subscript(path: SubjectPath) -> bool:
    """Return true when a path contains a subscript that cannot become a pattern index."""
    return any(
        isinstance(part, SubscriptPathPart) and part.index is None
        for part in path.parts
    )
