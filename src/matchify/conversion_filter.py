"""Validated expressions for selecting stylistically desirable conversions."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from types import CodeType

import libcst as cst

from .access_path import AttributePathPart
from .conditions import (
    AndExpr,
    BoolExpr,
    HasAttrPredicate,
    IsInstancePredicate,
    LenPredicate,
    OrExpr,
    PathPredicate,
    ValuePredicate,
)

DEFAULT_CONVERSION_FILTER = "True"


@dataclass(frozen=True)
class ConversionMetrics:
    """Stable source and generated-result properties of one conversion."""

    branches: int = 0
    isinstance_checks: int = 0
    literal_checks: int = 0
    attribute_checks: int = 0
    sequence_checks: int = 0
    max_depth: int = 0
    patterns: int = 0
    pattern_nodes: int = 0
    class_patterns: int = 0
    sequence_patterns: int = 0
    or_alternatives: int = 0
    max_pattern_depth: int = 0
    guarded_cases: int = 0
    guard_conditions: int = 0
    captures: int = 0

    @classmethod
    def ordered_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))

    @classmethod
    def names(cls) -> frozenset[str]:
        return frozenset(cls.ordered_names())


@dataclass(frozen=True)
class ConversionFilterDiagnostic:
    """A convertible chain rejected by the user's stylistic filter."""

    line: int
    column: int


@dataclass(frozen=True)
class ConversionFilter:
    """A restricted, prevalidated expression over conversion metrics."""

    expression: str

    @classmethod
    def parse(cls, expression: str) -> ConversionFilter:
        _compile_expression(expression)
        return cls(expression)

    def matches(self, metrics: ConversionMetrics) -> bool:
        values = {name: getattr(metrics, name) for name in metrics.names()}
        return bool(
            eval(_compile_expression(self.expression), {"__builtins__": {}}, values)
        )


@lru_cache(maxsize=128)
def _compile_expression(expression: str) -> CodeType:
    # Keep code objects in a process-local cache so filters remain picklable.
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ValueError(f"Invalid --convert-if expression: {error.msg}") from error
    _validate_expression(tree)
    return compile(tree, "<convert-if>", "eval")


def source_metrics(conditions: tuple[BoolExpr, ...]) -> ConversionMetrics:
    predicates = tuple(
        predicate
        for condition in conditions
        for predicate in _flatten_condition(condition)
    )
    paths = tuple(
        predicate.path
        for predicate in predicates
        if isinstance(predicate, PathPredicate)
    )
    return ConversionMetrics(
        branches=len(conditions),
        isinstance_checks=sum(
            isinstance(item, IsInstancePredicate) for item in predicates
        ),
        literal_checks=sum(isinstance(item, ValuePredicate) for item in predicates),
        attribute_checks=sum(
            isinstance(item, HasAttrPredicate)
            or (
                isinstance(item, PathPredicate)
                and any(isinstance(part, AttributePathPart) for part in item.path.parts)
            )
            for item in predicates
        ),
        sequence_checks=sum(isinstance(item, LenPredicate) for item in predicates),
        max_depth=max((len(path.parts) for path in paths), default=0),
    )


def with_generated_metrics(
    metrics: ConversionMetrics, match_statement: cst.Match
) -> ConversionMetrics:
    pattern_nodes = tuple(
        pattern
        for case in match_statement.cases
        for pattern in _walk_patterns(case.pattern)
    )
    return replace(
        metrics,
        patterns=sum(not _is_wildcard(case.pattern) for case in match_statement.cases),
        pattern_nodes=len(pattern_nodes),
        class_patterns=sum(
            isinstance(pattern, cst.MatchClass) for pattern in pattern_nodes
        ),
        sequence_patterns=sum(
            isinstance(pattern, cst.MatchSequence) for pattern in pattern_nodes
        ),
        or_alternatives=sum(
            len(pattern.patterns)
            for pattern in pattern_nodes
            if isinstance(pattern, cst.MatchOr)
        ),
        max_pattern_depth=max(
            (_pattern_depth(case.pattern) for case in match_statement.cases), default=0
        ),
        guarded_cases=sum(case.guard is not None for case in match_statement.cases),
        guard_conditions=sum(
            len(tuple(_flatten_boolean_cst(case.guard)))
            for case in match_statement.cases
            if case.guard is not None
        ),
        captures=sum(
            len(set(_capture_names(case.pattern))) for case in match_statement.cases
        ),
    )


def _flatten_condition(condition: BoolExpr) -> Iterator[BoolExpr]:
    if isinstance(condition, (AndExpr, OrExpr)):
        for part in condition.parts:
            yield from _flatten_condition(part)
    else:
        yield condition


def _flatten_boolean_cst(
    expression: cst.BaseExpression,
) -> Iterator[cst.BaseExpression]:
    if isinstance(expression, cst.BooleanOperation):
        yield from _flatten_boolean_cst(expression.left)
        yield from _flatten_boolean_cst(expression.right)
    else:
        yield expression


def _is_wildcard(pattern: cst.MatchPattern) -> bool:
    return (
        isinstance(pattern, cst.MatchAs)
        and pattern.pattern is None
        and pattern.name is None
    )


def _walk_patterns(pattern: cst.MatchPattern) -> Iterator[cst.MatchPattern]:
    yield pattern
    if isinstance(pattern, cst.MatchClass):
        for positional in pattern.patterns:
            yield from _walk_patterns(positional.value)
        for keyword in pattern.kwds:
            yield from _walk_patterns(keyword.pattern)
    elif isinstance(pattern, cst.MatchSequence):
        for sequence_item in pattern.patterns:
            if isinstance(sequence_item, cst.MatchSequenceElement):
                yield from _walk_patterns(sequence_item.value)
    elif isinstance(pattern, cst.MatchMapping):
        for mapping_item in pattern.elements:
            yield from _walk_patterns(mapping_item.pattern)
    elif isinstance(pattern, cst.MatchOr):
        for alternative in pattern.patterns:
            yield from _walk_patterns(alternative.pattern)
    elif isinstance(pattern, cst.MatchAs) and pattern.pattern is not None:
        yield from _walk_patterns(pattern.pattern)


def _capture_names(pattern: cst.MatchPattern) -> Iterator[str]:
    if isinstance(pattern, cst.MatchAs):
        if pattern.name is not None:
            yield pattern.name.value
        if pattern.pattern is not None:
            yield from _capture_names(pattern.pattern)
    elif isinstance(pattern, cst.MatchClass):
        for positional in pattern.patterns:
            yield from _capture_names(positional.value)
        for keyword in pattern.kwds:
            yield from _capture_names(keyword.pattern)
    elif isinstance(pattern, cst.MatchSequence):
        for sequence_item in pattern.patterns:
            if isinstance(sequence_item, cst.MatchSequenceElement):
                yield from _capture_names(sequence_item.value)
            elif sequence_item.name is not None and sequence_item.name.value != "_":
                yield sequence_item.name.value
    elif isinstance(pattern, cst.MatchMapping):
        for mapping_item in pattern.elements:
            yield from _capture_names(mapping_item.pattern)
        if pattern.rest is not None:
            yield pattern.rest.value
    elif isinstance(pattern, cst.MatchOr):
        for alternative in pattern.patterns:
            yield from _capture_names(alternative.pattern)


def _pattern_depth(pattern: cst.MatchPattern) -> int:
    if _is_wildcard(pattern):
        return 0
    if isinstance(pattern, cst.MatchClass):
        children: list[cst.MatchPattern] = [item.value for item in pattern.patterns]
        children.extend(item.pattern for item in pattern.kwds)
        return 1 + max((_pattern_depth(child) for child in children), default=0)
    if isinstance(pattern, cst.MatchSequence):
        sequence_depths = (
            (
                _pattern_depth(sequence_item.value)
                if isinstance(sequence_item, cst.MatchSequenceElement)
                else 1
            )
            for sequence_item in pattern.patterns
        )
        return 1 + max(sequence_depths, default=0)
    if isinstance(pattern, cst.MatchMapping):
        mapping_depths = [
            _pattern_depth(mapping_item.pattern) for mapping_item in pattern.elements
        ]
        if pattern.rest is not None:
            mapping_depths.append(1)
        return 1 + max(mapping_depths, default=0)
    if isinstance(pattern, cst.MatchOr):
        return 1 + max(
            _pattern_depth(alternative.pattern) for alternative in pattern.patterns
        )
    if isinstance(pattern, cst.MatchAs) and pattern.pattern is not None:
        return 1 + _pattern_depth(pattern.pattern)
    return 1


def _validate_expression(tree: ast.Expression) -> None:
    allowed_names = ConversionMetrics.names()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in allowed_names:
                names = ", ".join(sorted(allowed_names))
                raise ValueError(
                    f"Unknown --convert-if variable: {node.id}. Available: {names}"
                )
        elif isinstance(
            node,
            (
                ast.Expression,
                ast.BoolOp,
                ast.And,
                ast.Or,
                ast.BinOp,
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.UnaryOp,
                ast.Not,
                ast.Compare,
                ast.Lt,
                ast.LtE,
                ast.Eq,
                ast.NotEq,
                ast.GtE,
                ast.Gt,
                ast.Load,
            ),
        ) or (isinstance(node, ast.Constant) and type(node.value) in (bool, int)):
            continue
        else:
            raise ValueError(
                f"Unsupported syntax in --convert-if expression: {type(node).__name__}"
            )
