"""Validated expressions for selecting stylistically desirable conversions."""

from __future__ import annotations

import ast
from dataclasses import dataclass, fields, replace

import libcst as cst
from libcst import matchers as m

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
    def names(cls) -> frozenset[str]:
        return frozenset(field.name for field in fields(cls))


@dataclass(frozen=True)
class ConversionFilterDiagnostic:
    """A convertible chain rejected by the user's stylistic filter."""

    line: int
    column: int


@dataclass(frozen=True)
class ConversionFilter:
    """A restricted, prevalidated expression over conversion metrics."""

    expression: str
    tree: ast.Expression

    @classmethod
    def parse(cls, expression: str) -> ConversionFilter:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as error:
            raise ValueError(f"Invalid --convert-if expression: {error.msg}") from error
        _validate_expression(tree)
        return cls(expression, tree)

    def matches(self, metrics: ConversionMetrics) -> bool:
        values = {name: getattr(metrics, name) for name in metrics.names()}
        return bool(_evaluate(self.tree.body, values))


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
        captures=len(m.findall(match_statement, m.MatchAs(name=m.Name()))),
    )


def _flatten_condition(condition: BoolExpr):
    if isinstance(condition, (AndExpr, OrExpr)):
        for part in condition.parts:
            yield from _flatten_condition(part)
    else:
        yield condition


def _flatten_boolean_cst(expression: cst.BaseExpression):
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


def _walk_patterns(pattern: cst.MatchPattern):
    yield pattern
    if isinstance(pattern, cst.MatchClass):
        for item in pattern.patterns:
            yield from _walk_patterns(item.value)
        for item in pattern.kwds:
            yield from _walk_patterns(item.pattern)
    elif isinstance(pattern, cst.MatchSequence):
        for item in pattern.patterns:
            if isinstance(item, cst.MatchSequenceElement):
                yield from _walk_patterns(item.value)
    elif isinstance(pattern, cst.MatchMapping):
        for item in pattern.elements:
            yield from _walk_patterns(item.pattern)
    elif isinstance(pattern, cst.MatchOr):
        for item in pattern.patterns:
            yield from _walk_patterns(item.pattern)
    elif isinstance(pattern, cst.MatchAs) and pattern.pattern is not None:
        yield from _walk_patterns(pattern.pattern)


def _pattern_depth(pattern: cst.MatchPattern) -> int:
    if _is_wildcard(pattern):
        return 0
    if isinstance(pattern, cst.MatchClass):
        children = [item.value for item in pattern.patterns]
        children.extend(item.pattern for item in pattern.kwds)
        return 1 + max((_pattern_depth(child) for child in children), default=0)
    if isinstance(pattern, cst.MatchSequence):
        children = (
            (
                _pattern_depth(item.value)
                if isinstance(item, cst.MatchSequenceElement)
                else 1
            )
            for item in pattern.patterns
        )
        return 1 + max(children, default=0)
    if isinstance(pattern, cst.MatchMapping):
        children = [_pattern_depth(item.pattern) for item in pattern.elements]
        if pattern.rest is not None:
            children.append(1)
        return 1 + max(children, default=0)
    if isinstance(pattern, cst.MatchOr):
        return 1 + max(_pattern_depth(item.pattern) for item in pattern.patterns)
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


def _evaluate(node: ast.expr, values: dict[str, int]) -> int | float | bool:
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp):
        return not _evaluate(node.operand, values)
    if isinstance(node, ast.BoolOp):
        operands = (_evaluate(value, values) for value in node.values)
        return all(operands) if isinstance(node.op, ast.And) else any(operands)
    if isinstance(node, ast.BinOp):
        return _arithmetic(
            _evaluate(node.left, values), node.op, _evaluate(node.right, values)
        )
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, values)
        for operator, comparator_node in zip(node.ops, node.comparators):
            right = _evaluate(comparator_node, values)
            if not _compare(left, operator, right):
                return False
            left = right
        return True
    raise AssertionError(  # pragma: no cover - validation rejects other nodes
        f"Unexpected validated expression node: {type(node).__name__}"
    )


def _arithmetic(
    left: int | float | bool,
    operator: ast.operator,
    right: int | float | bool,
) -> int | float:
    if isinstance(operator, ast.Add):
        return left + right
    if isinstance(operator, ast.Sub):
        return left - right
    if isinstance(operator, ast.Mult):
        return left * right
    if isinstance(operator, ast.Div):
        return left / right
    raise AssertionError(  # pragma: no cover - validation rejects other operators
        f"Unexpected validated arithmetic operator: {type(operator).__name__}"
    )


def _compare(
    left: int | float | bool,
    operator: ast.cmpop,
    right: int | float | bool,
) -> bool:
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.GtE):
        return left >= right
    if isinstance(operator, ast.Gt):
        return left > right
    raise AssertionError(  # pragma: no cover - validation rejects other operators
        f"Unexpected validated comparison: {type(operator).__name__}"
    )
