"""Boolean condition IR used before lowering predicates into match patterns."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .patterns import (
    extract_isinstance_classes,
    flatten_boolean,
    is_literal_value,
    is_singleton_name,
)
from .subject_path import SubjectPath, SubscriptPathPart


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
    path: SubjectPath
    classes: tuple[cst.BaseExpression, ...]
    original: cst.BaseExpression


@dataclass(frozen=True)
class LenEqualsPredicate:
    path: SubjectPath
    length: int
    original: cst.BaseExpression


@dataclass(frozen=True)
class LenAtLeastPredicate:
    path: SubjectPath
    minimum: int
    original: cst.BaseExpression


@dataclass(frozen=True)
class SequenceTypePredicate:
    path: SubjectPath
    original: cst.BaseExpression


@dataclass(frozen=True)
class EqualsPredicate:
    path: SubjectPath
    value: cst.BaseExpression
    original: cst.BaseExpression


@dataclass(frozen=True)
class IsPredicate:
    path: SubjectPath
    value: cst.BaseExpression
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
    | RawPredicate
)
BoolExpr = AndExpr | OrExpr | Predicate


def parse_condition(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
) -> BoolExpr:
    """Parse a Python condition into a logical tree with typed predicates."""
    # LibCST BooleanOperation currently only exposes And/Or operators.
    if isinstance(condition, cst.BooleanOperation):  # pragma: no branch
        if isinstance(condition.operator, cst.And):
            return AndExpr(
                tuple(
                    parse_condition(part, subject, ignore_types_pattern)
                    for part in flatten_boolean(condition, cst.And)
                ),
                condition,
            )
        if isinstance(condition.operator, cst.Or):  # pragma: no branch
            return OrExpr(
                tuple(
                    parse_condition(part, subject, ignore_types_pattern)
                    for part in flatten_boolean(condition, cst.Or)
                ),
                condition,
            )
    return parse_predicate(condition, subject, ignore_types_pattern)


def parse_predicate(
    predicate: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
) -> Predicate:
    if isinstance(predicate, cst.Call) and m.matches(
        predicate, m.Call(func=m.Name(value="isinstance"))
    ):
        parsed = parse_isinstance_predicate(predicate, subject, ignore_types_pattern)
        if parsed is not None:
            return parsed

    if isinstance(predicate, cst.Comparison) and len(predicate.comparisons) == 1:
        parsed = parse_len_predicate(predicate, subject)
        if parsed is not None:
            return parsed
        parsed = parse_value_predicate(predicate, subject)
        if parsed is not None:
            return parsed

    return RawPredicate(predicate)


def parse_isinstance_predicate(
    predicate: cst.Call,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> IsInstancePredicate | SequenceTypePredicate | None:
    # The compiler rejects malformed direct-subject isinstance calls before
    # normalization; this keeps direct use of the parser defensive.
    if len(predicate.args) < 2:  # pragma: no cover
        return None
    path = SubjectPath.from_expression(predicate.args[0].value, subject)
    if path is None or has_unknown_subscript(path):
        return None
    classes = extract_isinstance_classes(predicate.args[1].value, ignore_types_pattern)
    if classes is None:
        return None
    if is_list_tuple_classes(classes):
        return SequenceTypePredicate(path, predicate)
    return IsInstancePredicate(path, tuple(classes), predicate)


def parse_len_predicate(
    predicate: cst.Comparison, subject: cst.BaseExpression
) -> LenEqualsPredicate | LenAtLeastPredicate | None:
    if not isinstance(predicate.left, cst.Call) or not m.matches(
        predicate.left,
        m.Call(func=m.Name(value="len"), args=[m.Arg()]),
    ):
        return None
    len_call = predicate.left
    path = SubjectPath.from_expression(len_call.args[0].value, subject)
    if path is None or has_unknown_subscript(path):
        return None
    target = predicate.comparisons[0]
    if not isinstance(target.comparator, cst.Integer):
        return None
    length = int(target.comparator.value)
    if isinstance(target.operator, cst.Equal):
        return LenEqualsPredicate(path, length, predicate)
    if isinstance(target.operator, cst.GreaterThanEqual):
        return LenAtLeastPredicate(path, length, predicate)
    return None


def parse_value_predicate(
    predicate: cst.Comparison, subject: cst.BaseExpression
) -> EqualsPredicate | IsPredicate | None:
    path = SubjectPath.from_expression(predicate.left, subject)
    if path is None or has_unknown_subscript(path):
        return None
    target = predicate.comparisons[0]
    if isinstance(target.operator, cst.Equal) and is_literal_value(target.comparator):
        return EqualsPredicate(path, target.comparator, predicate)
    if isinstance(target.operator, cst.Is) and is_singleton_name(target.comparator):
        return IsPredicate(path, target.comparator, predicate)
    return None


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


def is_list_tuple_classes(classes: list[cst.BaseExpression]) -> bool:
    names = []
    for class_expr in classes:
        # Exact list/tuple detection only applies to plain names; complex
        # classinfo is handled as a normal pattern candidate and validated later.
        if not isinstance(class_expr, cst.Name):  # pragma: no cover
            return False
        names.append(class_expr.value)
    return set(names) == {"list", "tuple"}


def has_unknown_subscript(path: SubjectPath) -> bool:
    """Return true when a path contains a subscript that cannot become a pattern index."""
    return any(
        isinstance(part, SubscriptPathPart) and part.index is None
        for part in path.parts
    )
