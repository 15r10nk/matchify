"""Lower typed condition predicates into the existing recursive pattern IR."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .conditions import (
    AndExpr,
    BoolExpr,
    EqualsPredicate,
    IsInstancePredicate,
    IsPredicate,
    LenAtLeastPredicate,
    LenEqualsPredicate,
    OrExpr,
    Predicate,
    RawPredicate,
    SequenceTypePredicate,
    parse_condition,
    residual_condition,
)
from .facts import (
    BranchFacts,
    ClassFact,
    OrFact,
    PathFact,
    PatternTree,
    SequenceFact,
    ValueFact,
)
from .subject_path import SubjectPath, SubscriptPathPart


@dataclass(frozen=True)
class PatternBuildResult:
    facts: tuple[PathFact, ...]
    residual: BoolExpr | None = None


def normalize_with_bool_tree(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None = r".*_TYPES$",
) -> BranchFacts | None:
    """Normalize one branch by parsing it into BoolExpr first."""
    expr = parse_condition(condition, subject, ignore_types_pattern)
    result = build_pattern(expr)
    if not result.facts:
        return None

    guard = residual_condition(result.residual)
    try:
        branch = BranchFacts(
            pattern=PatternTree.from_facts(result.facts),
            guard=guard,
        )
        # Non-empty facts above mean PatternTree.from_facts builds a pattern.
        if branch.pattern is not None:  # pragma: no branch
            branch.pattern.render()
    except ValueError:
        return None
    return branch


def build_pattern(
    expr: BoolExpr, *, require_anchored: bool = True
) -> PatternBuildResult:
    if isinstance(expr, AndExpr):
        return build_and_pattern(expr, require_anchored=require_anchored)
    if isinstance(expr, OrExpr):
        return build_or_pattern(expr)
    return build_predicate_pattern(expr)


def build_predicate_pattern(predicate: Predicate) -> PatternBuildResult:
    fact = fact_from_predicate(predicate)
    if fact is None:
        return PatternBuildResult((), predicate)
    return PatternBuildResult((fact,))


def build_and_pattern(
    expr: AndExpr, *, require_anchored: bool = True
) -> PatternBuildResult:
    facts: list[PathFact] = []
    residuals: list[BoolExpr] = []
    class_paths: set[SubjectPath] = set()

    for part in expr.parts:
        if isinstance(part, IsInstancePredicate) and part.path in class_paths:
            residuals.append(part)
            continue
        result = build_pattern(part)
        for fact in result.facts:
            if isinstance(fact, ClassFact):
                class_paths.add(fact.path)
            facts.append(fact)
        if result.residual is not None:
            residuals.append(result.residual)

    ordered_facts = order_facts(tuple(facts))
    residuals = drop_redundant_sequence_type_residuals(residuals, ordered_facts)
    if require_anchored and not facts_are_anchored(ordered_facts):
        return PatternBuildResult((), expr)

    residual = None
    if len(residuals) == 1:
        residual = residuals[0]
    elif residuals:
        residual = AndExpr(tuple(residuals), expr.original)

    return PatternBuildResult(
        ordered_facts,
        residual,
    )


def build_or_pattern(expr: OrExpr) -> PatternBuildResult:
    alternatives: list[tuple[PathFact, ...]] = []
    residuals: list[BoolExpr | None] = []

    for part in expr.parts:
        result = build_pattern(part, require_anchored=False)
        if not result.facts:
            return PatternBuildResult((), expr)
        alternatives.append(result.facts)
        residuals.append(result.residual)

    residuals = drop_common_sequence_type_residuals(residuals, alternatives)
    residual = common_residual(residuals)
    if residual is _MIXED_RESIDUALS:
        return PatternBuildResult((), expr)
    residual_cst = residual_condition(residual)
    if residual_cst is not None and not is_liftable_or_residual(residual_cst):
        return PatternBuildResult((), expr)

    common_path = common_alternative_path(alternatives)
    # Current alternatives share a normalized SubjectPath; this fallback keeps
    # future alternative shapes conservative.
    if common_path is None:  # pragma: no cover
        return PatternBuildResult(
            (OrFact(SubjectPath(()), tuple(alternatives)),),
            residual,
        )

    stripped = tuple(
        strip_alternative_prefix(common_path, facts) for facts in alternatives
    )
    return PatternBuildResult((OrFact(common_path, stripped),), residual)


def fact_from_predicate(predicate: Predicate) -> PathFact | None:
    if isinstance(predicate, EqualsPredicate | IsPredicate):
        return ValueFact(predicate.path, predicate.value)
    if isinstance(predicate, IsInstancePredicate):
        return ClassFact(predicate.path, predicate.classes)
    if isinstance(predicate, LenEqualsPredicate):
        return SequenceFact(predicate.path, predicate.length)
    if isinstance(predicate, LenAtLeastPredicate):
        return SequenceFact(predicate.path, predicate.minimum, use_star=True)
    if isinstance(predicate, SequenceTypePredicate):
        return None
    if isinstance(predicate, RawPredicate):
        return None
    # Predicate is a closed union; this is retained for defensive future edits.
    return None  # pragma: no cover


def drop_redundant_sequence_type_residuals(
    residuals: list[BoolExpr], facts: tuple[PathFact, ...]
) -> list[BoolExpr]:
    return [
        residual
        for residual in residuals
        if not (
            isinstance(residual, SequenceTypePredicate)
            and sequence_path_has_element_fact(residual.path, facts)
        )
    ]


def drop_common_sequence_type_residuals(
    residuals: list[BoolExpr | None],
    alternatives: list[tuple[PathFact, ...]],
) -> list[BoolExpr | None]:
    if not residuals or any(
        not isinstance(residual, SequenceTypePredicate) for residual in residuals
    ):
        return residuals
    first = residuals[0]
    if not isinstance(first, SequenceTypePredicate):
        return residuals
    if not all(
        isinstance(residual, SequenceTypePredicate) and residual.path == first.path
        for residual in residuals
    ):
        return residuals
    if not all(
        any(
            isinstance(fact, SequenceFact) and fact.path == first.path
            for fact in alternative
        )
        for alternative in alternatives
    ):
        return residuals
    return [None for _ in residuals]


def sequence_path_has_element_fact(
    path: SubjectPath, facts: tuple[PathFact, ...]
) -> bool:
    for fact in facts:
        if not fact.path.starts_with(path) or fact.path == path:
            continue
        relative = fact.path.strip_prefix(path)
        if isinstance(relative.first_part, SubscriptPathPart):
            return True
    return False


def order_facts(facts: tuple[PathFact, ...]) -> tuple[PathFact, ...]:
    return tuple(sorted(facts, key=fact_sort_key))


def fact_sort_key(fact: PathFact) -> tuple[int, int]:
    return (len(fact.path.parts), fact_priority(fact))


def fact_priority(fact: PathFact) -> int:
    if isinstance(fact, ClassFact | SequenceFact):
        return 0
    if isinstance(fact, OrFact) and all(
        alternative_is_anchor(alternative) for alternative in fact.alternatives
    ):
        return 0
    return 1


def alternative_is_anchor(
    alternative: ValueFact | ClassFact | tuple[PathFact, ...],
) -> bool:
    if isinstance(alternative, ClassFact):
        return True
    if isinstance(alternative, tuple):
        return bool(alternative) and isinstance(
            alternative[0], ClassFact | SequenceFact
        )
    return False


def facts_are_anchored(facts: tuple[PathFact, ...]) -> bool:
    if not facts:
        return False

    anchored_paths: set[SubjectPath] = set()
    for fact in facts:
        if fact.path.is_subject:
            if isinstance(fact, ClassFact | SequenceFact) or (
                isinstance(fact, OrFact) and or_fact_is_anchor(fact)
            ):
                anchored_paths.add(fact.path)
            if isinstance(fact, ValueFact | ClassFact | SequenceFact | OrFact):
                continue

        parent = required_anchor_path(fact.path)
        if parent is None:
            return False
        if not any(
            parent == anchor or parent.starts_with(anchor) for anchor in anchored_paths
        ):
            return False
        if isinstance(fact, ClassFact | SequenceFact) or (
            isinstance(fact, OrFact) and or_fact_is_anchor(fact)
        ):
            anchored_paths.add(fact.path)

    return True


def required_anchor_path(path: SubjectPath) -> SubjectPath | None:
    if path.is_subject:
        return SubjectPath(())
    return path.parent()


def or_fact_is_anchor(fact: OrFact) -> bool:
    return all(alternative_is_anchor(alternative) for alternative in fact.alternatives)


_MIXED_RESIDUALS = object()


def common_residual(
    residuals: list[BoolExpr | None],
) -> BoolExpr | None | object:
    if all(residual is None for residual in residuals):
        return None
    if any(residual is None for residual in residuals):
        return _MIXED_RESIDUALS

    first = residuals[0]
    # Guarded by the `any(residual is None)` branch above.
    if first is None:  # pragma: no cover
        return _MIXED_RESIDUALS
    first_condition = residual_condition(first)
    # Concrete residual nodes always render back to a condition.
    if first_condition is None:  # pragma: no cover
        return _MIXED_RESIDUALS

    for residual in residuals[1:]:
        # Guarded by the `any(residual is None)` branch above.
        if residual is None:  # pragma: no cover
            return _MIXED_RESIDUALS
        condition = residual_condition(residual)
        # `condition is None` is defensive; unequal residuals are covered by E2E.
        if condition is None or not condition.deep_equals(first_condition):
            return _MIXED_RESIDUALS
    return first


def is_liftable_or_residual(guard: cst.BaseExpression) -> bool:
    unsafe_matcher = m.Call() | m.NamedExpr() | m.Await() | m.Yield()
    return not m.findall(guard, unsafe_matcher)


def common_alternative_path(
    alternatives: list[tuple[PathFact, ...]],
) -> SubjectPath | None:
    if not alternatives or any(not facts for facts in alternatives):
        return None
    first_path = alternatives[0][0].path
    if all(
        all(fact.path.starts_with(first_path) for fact in facts)
        for facts in alternatives
    ):
        return first_path
    return None


def strip_alternative_prefix(
    path: SubjectPath, facts: tuple[PathFact, ...]
) -> ValueFact | ClassFact | tuple[PathFact, ...]:
    stripped = tuple(strip_fact_prefix(path, fact) for fact in facts)
    if len(stripped) != 1:
        return stripped
    fact = stripped[0]
    if isinstance(fact, ValueFact):
        return fact
    if isinstance(fact, ClassFact):
        return fact
    return stripped


def strip_fact_prefix(path: SubjectPath, fact: PathFact) -> PathFact:
    stripped_path = fact.path.strip_prefix(path)
    if isinstance(fact, ValueFact):
        return ValueFact(stripped_path, fact.value)
    if isinstance(fact, ClassFact):
        return ClassFact(stripped_path, fact.classes)
    if isinstance(fact, SequenceFact):
        return SequenceFact(stripped_path, fact.length, fact.use_star)
    return OrFact(stripped_path, fact.alternatives)
