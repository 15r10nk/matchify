"""Lower typed condition predicates into the recursive pattern IR."""

from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .access_path import (
    AccessPath,
    AccessPathPart,
    AttributePathPart,
    MatchSubjectPlan,
    MatchSubjectRoot,
    SubscriptPathPart,
)
from .conditions import (
    AndExpr,
    BoolExpr,
    IsInstancePredicate,
    LenPredicate,
    OrExpr,
    PathPredicate,
    RawPredicate,
    ValuePredicate,
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
from .patterns import is_class_pattern_expr, is_list_tuple_classes


@dataclass(frozen=True)
class PatternBuildResult:
    facts: tuple[PathFact, ...]
    residual: BoolExpr | None = None


def normalize_condition(
    expr: BoolExpr,
    subject: MatchSubjectPlan,
    *,
    allow_object_anchors: bool = False,
) -> BranchFacts:
    """Bind and lower a parsed condition into a pattern and residual guard."""
    expr = bind_condition_subject(expr, subject)
    expr = remove_implied_checks(expr)
    result = build_pattern(expr)
    facts = result.facts
    if subject.is_composite:
        facts = (
            SequenceFact(
                AccessPath(MatchSubjectRoot()),
                len(subject.subjects),
            ),
            *facts,
        )
    completed_facts = complete_pattern_parents(
        facts,
        infer_attribute_parents=allow_object_anchors,
    )
    if completed_facts is None:
        return BranchFacts(pattern=None, guard=expr.original)
    try:
        pattern = PatternTree.from_facts(completed_facts)
        pattern.render()
    except ValueError:
        return BranchFacts(pattern=None, guard=expr.original)

    guard = residual_condition(result.residual)
    return BranchFacts(pattern=pattern, guard=guard)


def complete_pattern_parents(
    facts: tuple[PathFact, ...],
    *,
    infer_attribute_parents: bool,
) -> tuple[PathFact, ...] | None:
    """Ensure every path edge has a compatible structural parent fact."""
    if not facts:
        return None

    parents = {fact.path: fact for fact in facts if fact_is_anchor(fact)}
    inferred: list[ClassFact] = []
    for fact in facts:
        parent_path = AccessPath(fact.path.root)
        for part in fact.path.parts:
            parent = parents.get(parent_path)
            if parent is None:
                if not infer_attribute_parents or not isinstance(
                    part, AttributePathPart
                ):
                    return None
                parent = ClassFact(parent_path, (cst.Name("object"),))
                parents[parent_path] = parent
                inferred.append(parent)
            if not fact_supports_child(parent, part):
                return None
            parent_path = AccessPath(parent_path.root, (*parent_path.parts, part))

    return tuple(
        sorted(
            (*inferred, *facts),
            key=lambda fact: (len(fact.path.parts), fact_priority(fact)),
        )
    )


def fact_supports_child(fact: PathFact, part: AccessPathPart) -> bool:
    if isinstance(part, AttributePathPart):
        return isinstance(fact, ClassFact) or (
            isinstance(fact, OrFact)
            and all(
                alternative and fact_supports_child(alternative[0], part)
                for alternative in fact.alternatives
            )
        )
    if isinstance(part, SubscriptPathPart):
        return isinstance(fact, SequenceFact) or (
            isinstance(fact, OrFact)
            and all(
                alternative and fact_supports_child(alternative[0], part)
                for alternative in fact.alternatives
            )
        )
    return False


def build_pattern(expr: BoolExpr) -> PatternBuildResult:
    if isinstance(expr, AndExpr):
        return build_and_pattern(expr)
    if isinstance(expr, OrExpr):
        return build_or_pattern(expr)
    if isinstance(expr, RawPredicate):
        return PatternBuildResult((), expr)
    fact = fact_from_predicate(expr)
    if fact is None:
        return PatternBuildResult((), expr)
    return PatternBuildResult((fact,))


def build_and_pattern(expr: AndExpr) -> PatternBuildResult:
    facts: list[PathFact] = []
    residuals: list[BoolExpr] = []
    class_paths: set[AccessPath] = set()

    for part in expr.parts:
        if is_sequence_pattern_type_check(part) and has_len_fact(part, expr.parts):
            residuals.append(part)
            continue
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
    residuals = drop_redundant_residuals(residuals, ordered_facts)
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
        result = build_pattern(part)
        if not result.facts:
            return PatternBuildResult((), expr)
        alternatives.append(result.facts)
        residuals.append(result.residual)

    residuals = drop_implied_or_residuals(residuals, alternatives)
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


def fact_from_predicate(predicate: PathPredicate) -> PathFact | None:
    if not predicate.path.is_patternable:
        return None
    if isinstance(predicate, ValuePredicate):
        if not predicate.allow_nested_pattern and not predicate.path.is_subject:
            return None
        return ValueFact(predicate.path, predicate.value)
    if isinstance(predicate, IsInstancePredicate):
        if not all(is_class_pattern_expr(cls) for cls in predicate.classes):
            return None
        return ClassFact(predicate.path, predicate.classes)
    if isinstance(predicate, LenPredicate):
        return SequenceFact(predicate.path, predicate.length, predicate.use_star)
    return None


def is_sequence_pattern_type_check(expr: BoolExpr | None) -> bool:
    return isinstance(expr, IsInstancePredicate) and is_list_tuple_classes(expr.classes)


def has_len_fact(predicate: IsInstancePredicate, parts: tuple[BoolExpr, ...]) -> bool:
    return any(
        isinstance(part, LenPredicate) and part.path == predicate.path for part in parts
    )


def drop_redundant_residuals(
    residuals: list[BoolExpr], facts: tuple[PathFact, ...]
) -> list[BoolExpr]:
    return [
        residual
        for residual in residuals
        if not residual_is_implied_by_facts(residual, facts)
    ]


def residual_is_implied_by_facts(
    residual: BoolExpr,
    facts: tuple[PathFact, ...],
) -> bool:
    return bool(
        is_sequence_pattern_type_check(residual)
        and sequence_path_has_element_fact(residual.path, facts)
    )


def drop_implied_or_residuals(
    residuals: list[BoolExpr | None],
    alternatives: list[tuple[PathFact, ...]],
) -> list[BoolExpr | None]:
    if not residuals or not all_residuals_are_implied_by_alternatives(
        residuals, alternatives
    ):
        return residuals
    return [None] * len(residuals)


def all_residuals_are_implied_by_alternatives(
    residuals: list[BoolExpr | None],
    alternatives: list[tuple[PathFact, ...]],
) -> bool:
    return all(
        residual is not None and residual_is_implied_by_alternative(residual, facts)
        for residual, facts in zip(
            residuals,
            alternatives,
            strict=True,
        )
    )


def residual_is_implied_by_alternative(
    residual: BoolExpr, facts: tuple[PathFact, ...]
) -> bool:
    return bool(
        is_sequence_pattern_type_check(residual)
        and (
            sequence_path_has_element_fact(residual.path, facts)
            or sequence_path_has_anchor_fact(residual.path, facts)
        )
    )


def sequence_path_has_element_fact(
    path: AccessPath, facts: tuple[PathFact, ...]
) -> bool:
    for fact in facts:
        if isinstance(fact.path.first_part_after(path), SubscriptPathPart):
            return True
    return False


def sequence_path_has_anchor_fact(
    path: AccessPath, facts: tuple[PathFact, ...]
) -> bool:
    return any(isinstance(fact, SequenceFact) and fact.path == path for fact in facts)


def fact_priority(fact: PathFact) -> int:
    return 0 if fact_is_anchor(fact) else 1


def fact_is_anchor(fact: PathFact) -> bool:
    return isinstance(fact, ClassFact | SequenceFact) or (
        isinstance(fact, OrFact) and or_fact_is_anchor(fact)
    )


def or_fact_is_anchor(fact: OrFact) -> bool:
    return all(
        alternative and isinstance(alternative[0], ClassFact | SequenceFact)
        for alternative in fact.alternatives
    )


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
