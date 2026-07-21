"""Lower typed condition predicates into the recursive pattern IR."""

from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .access_path import (
    AccessPath,
    MatchSubjectPlan,
    MatchSubjectRoot,
    SubscriptPathPart,
)
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
    bind_condition_subject,
    remove_implied_checks,
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


@dataclass(frozen=True)
class PatternBuildResult:
    facts: tuple[PathFact, ...]
    residual: BoolExpr | None = None


def normalize_condition(
    expr: BoolExpr,
    subject: MatchSubjectPlan,
) -> BranchFacts:
    """Bind and lower a parsed condition into a pattern and residual guard."""
    expr = bind_condition_subject(expr, subject)
    expr = remove_implied_checks(expr)
    result = build_pattern(expr, require_anchored=not subject.is_composite)
    facts = result.facts
    if subject.is_composite:
        facts = (
            SequenceFact(
                AccessPath(MatchSubjectRoot()),
                len(subject.subjects),
            ),
            *facts,
        )
    try:
        pattern = PatternTree.from_facts(facts)
        pattern.render()
    except ValueError:
        return BranchFacts(pattern=None, guard=expr.original)

    guard = residual_condition(result.residual)
    return BranchFacts(pattern=pattern, guard=guard)


def build_pattern(
    expr: BoolExpr, *, require_anchored: bool = True
) -> PatternBuildResult:
    if isinstance(expr, AndExpr):
        return build_and_pattern(expr, require_anchored=require_anchored)
    if isinstance(expr, OrExpr):
        return build_or_pattern(expr)
    fact = fact_from_predicate(expr)
    if fact is None:
        return PatternBuildResult((), expr)
    return PatternBuildResult((fact,))


def build_and_pattern(
    expr: AndExpr, *, require_anchored: bool = True
) -> PatternBuildResult:
    facts: list[PathFact] = []
    residuals: list[BoolExpr] = []
    class_paths: set[AccessPath] = set()

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

    ordered_facts = tuple(
        sorted(facts, key=lambda fact: (len(fact.path.parts), fact_priority(fact)))
    )
    residuals = drop_redundant_sequence_type_residuals(residuals, ordered_facts)
    if require_anchored and not facts_are_anchored(ordered_facts):
        return PatternBuildResult((), expr)

    residual = None
    if len(residuals) == 1:
        residual = residuals[0]
    elif residuals:
        residual = AndExpr(tuple(residuals), expr.original)

    return PatternBuildResult(ordered_facts, residual)


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
    if common_path is None:
        return PatternBuildResult((), expr)

    stripped = tuple(
        strip_alternative_prefix(common_path, facts) for facts in alternatives
    )
    return PatternBuildResult((OrFact(common_path, stripped),), residual)


def fact_from_predicate(predicate: Predicate) -> PathFact | None:
    if isinstance(predicate, RawPredicate | SequenceTypePredicate):
        return None
    if not predicate.path.is_patternable:
        return None
    if isinstance(predicate, EqualsPredicate | IsPredicate):
        return ValueFact(predicate.path, predicate.value)
    if isinstance(predicate, IsInstancePredicate):
        return ClassFact(predicate.path, predicate.classes)
    if isinstance(predicate, LenEqualsPredicate):
        return SequenceFact(predicate.path, predicate.length)
    if isinstance(predicate, LenAtLeastPredicate):
        return SequenceFact(predicate.path, predicate.minimum, use_star=True)
    return None


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
    if not all(residual.path == first.path for residual in residuals):
        return residuals
    if not all(
        any(
            isinstance(fact, SequenceFact) and fact.path == first.path
            for fact in alternative
        )
        for alternative in alternatives
    ):
        return residuals
    return [None] * len(residuals)


def sequence_path_has_element_fact(
    path: AccessPath, facts: tuple[PathFact, ...]
) -> bool:
    for fact in facts:
        if not fact.path.starts_with(path) or fact.path == path:
            continue
        relative = fact.path.strip_prefix(path)
        if isinstance(relative.first_part, SubscriptPathPart):
            return True
    return False


def fact_priority(fact: PathFact) -> int:
    return 0 if fact_is_anchor(fact) else 1


def fact_is_anchor(fact: PathFact) -> bool:
    return isinstance(fact, ClassFact | SequenceFact) or (
        isinstance(fact, OrFact) and or_fact_is_anchor(fact)
    )


def alternative_is_anchor(alternative: tuple[PathFact, ...]) -> bool:
    return bool(alternative) and isinstance(alternative[0], ClassFact | SequenceFact)


def facts_are_anchored(facts: tuple[PathFact, ...]) -> bool:
    if not facts:
        return False

    anchored_paths: set[AccessPath] = set()
    for fact in facts:
        if fact.path.is_subject:
            if fact_is_anchor(fact):
                anchored_paths.add(fact.path)
            continue

        parent = fact.path.parent()
        if not any(
            parent == anchor or parent.starts_with(anchor) for anchor in anchored_paths
        ):
            return False
        if fact_is_anchor(fact):
            anchored_paths.add(fact.path)

    return True


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
    first_condition = residual_condition(first)
    if any(
        not residual_condition(residual).deep_equals(first_condition)
        for residual in residuals[1:]
    ):
        return _MIXED_RESIDUALS
    return first


def is_liftable_or_residual(guard: cst.BaseExpression) -> bool:
    unsafe_matcher = m.Call() | m.NamedExpr() | m.Await() | m.Yield()
    return not m.findall(guard, unsafe_matcher)


def common_alternative_path(
    alternatives: list[tuple[PathFact, ...]],
) -> AccessPath | None:
    if not alternatives or any(not facts for facts in alternatives):
        return None
    first_path = alternatives[0][0].path
    return (
        first_path
        if all(
            all(fact.path.starts_with(first_path) for fact in facts)
            for facts in alternatives
        )
        else None
    )


def strip_alternative_prefix(
    path: AccessPath, facts: tuple[PathFact, ...]
) -> tuple[PathFact, ...]:
    return tuple(strip_fact_prefix(path, fact) for fact in facts)


def strip_fact_prefix(path: AccessPath, fact: PathFact) -> PathFact:
    stripped_path = fact.path.strip_prefix(path)
    if isinstance(fact, ValueFact):
        return ValueFact(stripped_path, fact.value)
    if isinstance(fact, ClassFact):
        return ClassFact(stripped_path, fact.classes)
    if isinstance(fact, SequenceFact):
        return SequenceFact(stripped_path, fact.length, fact.use_star)
    return OrFact(stripped_path, fact.alternatives)
