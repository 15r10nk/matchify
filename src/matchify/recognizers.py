"""Recognizers that turn branch conditions into match patterns and guards."""

from __future__ import annotations

import libcst as cst
from libcst import matchers as m

from .facts import (
    BranchFacts,
    ClassFact,
    OrFact,
    PathFact,
    PatternTree,
    SequenceFact,
    ValueFact,
    replace_fact_path,
)
from .patterns import (
    combine_guards,
    extract_isinstance_classes,
    flatten_boolean,
    is_literal_value,
    is_singleton_name,
)
from .sequence_patterns import (
    WildcardElementPattern,
    find_sequence_subject,
    is_component_for_sequence_subject,
    validate_wildcard_constraint,
)
from .subject_path import (
    AttributePathPart,
    SubjectPath,
    SubscriptPathPart,
)


class SubjectRecognizer:
    """Extracts the expression that should become the `match` subject."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def recognize(self, test: cst.BaseExpression) -> cst.BaseExpression | None:
        or_subject = self._recognize_or_subject(test)
        if or_subject is not None:
            return or_subject

        if isinstance(test, cst.Call) and m.matches(
            test, m.Call(func=m.Name(value="isinstance"))
        ):
            if (
                len(test.args) >= 2
                and extract_isinstance_classes(
                    test.args[1].value, self.ignore_types_pattern
                )
                is not None
            ):
                return test.args[0].value

        if isinstance(test, cst.BooleanOperation) and isinstance(
            test.operator, cst.And
        ):
            isinstance_subject = self._find_isinstance_subject(
                test, include_subscripts=False
            )
            if isinstance_subject is not None:
                return isinstance_subject
            sequence_subject = find_sequence_subject(test)
            if sequence_subject is not None:
                return sequence_subject
            value_subject = self._find_value_subject(test)
            if value_subject is not None:
                return value_subject
            isinstance_subject = self._find_isinstance_subject(
                test, include_subscripts=True
            )
            if isinstance_subject is not None:
                return isinstance_subject

        sequence_subject = find_sequence_subject(test)
        if sequence_subject is not None:
            return sequence_subject

        if isinstance(test, cst.Comparison) and len(test.comparisons) == 1:
            operator = test.comparisons[0].operator
            if isinstance(operator, (cst.Equal, cst.Is)):
                return test.left

        return None

    def _recognize_or_subject(
        self, test: cst.BaseExpression
    ) -> cst.BaseExpression | None:
        parts = flatten_boolean(test, cst.Or)
        if len(parts) <= 1:
            return None

        subject: cst.BaseExpression | None = None
        for part in parts:
            part_subject = self._recognize_or_part_subject(part)
            if part_subject is None:
                return None
            if subject is None:
                subject = part_subject
            elif not part_subject.deep_equals(subject):
                return None

        return subject

    def _recognize_or_part_subject(
        self, part: cst.BaseExpression
    ) -> cst.BaseExpression | None:
        if isinstance(part, cst.Comparison) and len(part.comparisons) == 1:
            target = part.comparisons[0]
            if not isinstance(target.operator, (cst.Equal, cst.Is)):
                return None
            if isinstance(target.operator, cst.Is) and not is_singleton_name(
                target.comparator
            ):
                return None
            if not is_literal_value(target.comparator):
                return None
            return part.left

        if isinstance(part, cst.Call) and m.matches(
            part, m.Call(func=m.Name(value="isinstance"))
        ):
            if (
                len(part.args) >= 2
                and extract_isinstance_classes(
                    part.args[1].value, self.ignore_types_pattern
                )
                is not None
            ):
                return part.args[0].value

        if isinstance(part, cst.BooleanOperation) and isinstance(
            part.operator, cst.And
        ):
            return self.recognize(part)

        return None

    def _find_value_subject(
        self, test: cst.BaseExpression
    ) -> cst.BaseExpression | None:
        for component in flatten_boolean(test, cst.And):
            or_subject = self._recognize_or_subject(component)
            if or_subject is not None and not contains_subscript(or_subject):
                return or_subject

            if not isinstance(component, cst.Comparison):
                continue
            if len(component.comparisons) != 1:
                continue
            target = component.comparisons[0]
            if contains_subscript(component.left):
                continue
            if isinstance(target.operator, cst.Equal) and is_literal_value(
                target.comparator
            ):
                return component.left
            if isinstance(target.operator, cst.Is) and is_singleton_name(
                target.comparator
            ):
                return component.left
        return None

    def _find_isinstance_subject(
        self, test: cst.BaseExpression, include_subscripts: bool
    ) -> cst.BaseExpression | None:
        for component in flatten_boolean(test, cst.And):
            if isinstance(component, cst.Call) and m.matches(
                component, m.Call(func=m.Name(value="isinstance"))
            ):
                if (
                    len(component.args) >= 2
                    and extract_isinstance_classes(
                        component.args[1].value, self.ignore_types_pattern
                    )
                    is not None
                ):
                    if not include_subscripts and contains_subscript(
                        component.args[0].value
                    ):
                        continue
                    return component.args[0].value
        return None


_MIXED_OR_GUARDS = object()


def common_or_guard(
    guards: list[cst.BaseExpression | None],
) -> cst.BaseExpression | None | object:
    if all(guard is None for guard in guards):
        return None
    if any(guard is None for guard in guards):
        return _MIXED_OR_GUARDS

    first = guards[0]
    if first is None:
        return _MIXED_OR_GUARDS
    if all(guard is not None and guard.deep_equals(first) for guard in guards[1:]):
        return first
    return _MIXED_OR_GUARDS


def is_liftable_or_guard(guard: cst.BaseExpression) -> bool:
    unsafe_matcher = m.Call() | m.NamedExpr() | m.Await() | m.Yield()
    return not m.findall(guard, unsafe_matcher)


def remove_redundant_subject_checks(
    part: cst.BaseExpression,
    subject: cst.BaseExpression,
    *,
    remove_sequence_type_checks: bool = True,
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
            component, subject, checked_paths, remove_sequence_type_checks
        )
    ]
    if len(filtered) == len(components):
        return part
    if len(filtered) == 1:
        return filtered[0]
    combined = combine_guards(filtered)
    return combined if combined is not None else part


def is_redundant_hasattr(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
) -> bool:
    hasattr_path = extract_hasattr_attribute_path(node, subject)
    if hasattr_path is None:
        return False
    return any(
        path == hasattr_path or path.starts_with(hasattr_path) for path in checked_paths
    )


def is_redundant_sequence_type_check(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
) -> bool:
    sequence_path = extract_list_tuple_isinstance_path(node, subject)
    return sequence_path is not None and sequence_path in checked_paths


def should_remove_redundant_sequence_type_check(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
    remove_sequence_type_checks: bool,
) -> bool:
    if not is_redundant_sequence_type_check(node, subject, checked_paths):
        return False
    sequence_path = extract_list_tuple_isinstance_path(node, subject)
    return remove_sequence_type_checks or (
        sequence_path is not None and sequence_path.is_subject
    )


def extract_list_tuple_isinstance_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="isinstance"))
    ):
        return None
    if len(node.args) != 2:
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:
        return None
    class_arg = node.args[1].value
    if not isinstance(class_arg, cst.Tuple):
        return None
    class_names = []
    for element in class_arg.elements:
        if not isinstance(element, cst.Element) or not isinstance(
            element.value, cst.Name
        ):
            return None
        class_names.append(element.value.value)
    return path if set(class_names) == {"list", "tuple"} else None


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

    if isinstance(node, cst.Call) and m.matches(
        node, m.Call(func=m.Name(value="isinstance"))
    ):
        if len(node.args) < 2:
            return set()
        path = SubjectPath.from_expression(node.args[0].value, subject)
        if path is None or not path:
            return set()
        return {path}

    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return set()

    if m.matches(node.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
        len_call = node.left
        if not len_call.args:
            return set()
        path = SubjectPath.from_expression(len_call.args[0].value, subject)
        if path is None:
            return set()
        return {path}

    path = SubjectPath.from_expression(node.left, subject)
    if path is None or not path or not isinstance(path.last_part, AttributePathPart):
        return set()

    target = node.comparisons[0]
    if isinstance(target.operator, cst.Is) and not is_singleton_name(target.comparator):
        return set()
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return set()
    if not is_literal_value(target.comparator):
        return set()

    return {path}


def extract_hasattr_attribute_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"))
    ):
        return None
    if len(node.args) != 2:
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:
        return None
    name_arg = node.args[1].value
    if not isinstance(name_arg, cst.SimpleString):
        return None
    try:
        value = cst.ensure_type(cst.parse_expression(name_arg.value), cst.SimpleString)
    except cst.ParserSyntaxError:
        return None
    literal = value.evaluated_value
    if not isinstance(literal, str):
        return None
    return SubjectPath((*path.parts, AttributePathPart(literal)))


def is_sequence_subject_guard_component(
    component: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    if isinstance(component, cst.BooleanOperation) and isinstance(
        component.operator, cst.Or
    ):
        parts = flatten_boolean(component, cst.Or)
        return all(
            is_component_for_sequence_subject(part, subject) for part in parts
        ) and any(is_sequence_subject_guard_component(part, subject) for part in parts)

    if not isinstance(component, cst.Comparison) or len(component.comparisons) != 1:
        return False
    if not is_component_for_sequence_subject(component, subject):
        return False

    if m.matches(component.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
        return False

    target = component.comparisons[0]
    if isinstance(target.operator, cst.Equal) and not is_literal_value(
        target.comparator
    ):
        path = SubjectPath.from_expression(component.left, subject)
        return path is not None and path.starts_with_subscript

    path = SubjectPath.from_expression(component.left, subject)
    if path is not None and len(path.parts) == 1 and path.starts_with_subscript:
        return not isinstance(target.operator, (cst.Equal, cst.Is))

    return not isinstance(target.operator, (cst.Equal, cst.Is))


class PatternRecognitionEngine:
    """Runs branch recognizers in order, from specific to conservative."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern
        self.subject_recognizer = SubjectRecognizer(ignore_types_pattern)

    def recognize_subject(self, test: cst.BaseExpression) -> cst.BaseExpression | None:
        return self.subject_recognizer.recognize(test)

    def normalize_branch(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> BranchFacts:
        or_facts = normalize_or_branch_facts(
            condition, subject, self.ignore_types_pattern
        )
        if or_facts is not None:
            return or_facts

        fact_backed_branch = normalize_fact_backed_branch(
            condition, subject, self.ignore_types_pattern
        )
        if fact_backed_branch is not None:
            return fact_backed_branch

        return BranchFacts(
            condition=condition,
            subject=subject,
            facts=(),
            pattern=None,
            guard=condition,
        )


def normalize_or_branch_facts(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> BranchFacts | None:
    parts = flatten_boolean(condition, cst.Or)
    if len(parts) <= 1:
        return None

    facts: list[ValueFact | ClassFact | SequenceFact] = []
    patterns: list[PatternTree] = []
    guards: list[cst.BaseExpression | None] = []
    for part in parts:
        part = remove_redundant_subject_checks(part, subject)
        branch = normalize_fact_backed_branch(
            part,
            subject,
            ignore_types_pattern,
            allow_subject_guard=True,
            remove_sequence_type_checks=True,
        )
        if branch is None or branch.pattern is None:
            return None
        facts.extend(branch.facts)
        patterns.append(branch.pattern)
        guards.append(branch.guard)

    common_guard = common_or_guard(guards)
    if common_guard is _MIXED_OR_GUARDS:
        return None
    if common_guard is not None and not is_liftable_or_guard(common_guard):
        return None

    return BranchFacts.from_or_patterns(
        condition,
        subject,
        tuple(facts),
        tuple(patterns),
        guard=common_guard,
    )


def normalize_fact_backed_branch(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
    *,
    allow_subject_guard: bool = False,
    remove_sequence_type_checks: bool = False,
) -> BranchFacts | None:
    condition = remove_redundant_subject_checks(
        condition,
        subject,
        remove_sequence_type_checks=remove_sequence_type_checks,
    )
    branch = normalize_unguarded_fact_backed_branch(
        condition, subject, ignore_types_pattern
    )
    if branch is not None:
        return branch
    return normalize_guarded_fact_backed_branch(
        condition,
        subject,
        ignore_types_pattern,
        allow_subject_guard=allow_subject_guard,
    )


def normalize_unguarded_fact_backed_branch(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> BranchFacts | None:
    value_fact = normalize_subject_value_fact(condition, subject)
    if value_fact is not None:
        return BranchFacts.from_value_fact(condition, subject, value_fact)

    class_fact = normalize_subject_class_fact(condition, subject, ignore_types_pattern)
    if class_fact is not None:
        return BranchFacts.from_class_fact(condition, subject, class_fact)

    class_attribute_facts = normalize_subject_class_attribute_facts(
        condition, subject, ignore_types_pattern
    )
    if class_attribute_facts is not None:
        (
            class_fact,
            attribute_value_facts,
            attribute_class_facts,
            attribute_sequence_facts,
            attribute_or_facts,
        ) = class_attribute_facts
        return BranchFacts.from_class_fact(
            condition,
            subject,
            class_fact,
            value_facts=attribute_value_facts,
            class_facts=attribute_class_facts,
            sequence_facts=attribute_sequence_facts,
            or_facts=attribute_or_facts,
        )

    sequence_facts = normalize_subject_sequence_facts(
        condition, subject, ignore_types_pattern
    )
    if sequence_facts is None:
        return None

    (
        sequence_fact,
        sequence_value_facts,
        sequence_class_facts,
        sequence_sequence_facts,
        sequence_or_facts,
    ) = sequence_facts
    return BranchFacts.from_sequence_fact(
        condition,
        subject,
        sequence_fact,
        value_facts=sequence_value_facts,
        class_facts=sequence_class_facts,
        sequence_facts=sequence_sequence_facts,
        or_facts=sequence_or_facts,
    )


def normalize_guarded_fact_backed_branch(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
    *,
    allow_subject_guard: bool = False,
) -> BranchFacts | None:
    if not isinstance(condition, cst.BooleanOperation) or not isinstance(
        condition.operator, cst.And
    ):
        return None

    pattern_components: list[cst.BaseExpression] = []
    guard_components: list[cst.BaseExpression] = []
    has_subject_class_pattern = False
    for component in flatten_boolean(condition, cst.And):
        class_fact = normalize_subject_class_fact(
            component, subject, ignore_types_pattern
        )
        if class_fact is not None:
            if has_subject_class_pattern:
                guard_components.append(component)
                continue
            has_subject_class_pattern = True
            pattern_components.append(component)
            continue
        if is_fact_backed_pattern_component(component, subject, ignore_types_pattern):
            pattern_components.append(component)
        else:
            guard_components.append(component)

    if not pattern_components or not guard_components:
        return None

    pattern_condition = combine_guards(pattern_components)
    if pattern_condition is None:
        return None

    branch = normalize_unguarded_fact_backed_branch(
        pattern_condition, subject, ignore_types_pattern
    )
    if branch is None:
        branch = normalize_or_branch_facts(
            pattern_condition, subject, ignore_types_pattern
        )
    if branch is None:
        sequence_fact = normalize_sequence_length_fact(pattern_condition, subject)
        if sequence_fact is not None and sequence_fact.path.is_subject:
            branch = BranchFacts.from_sequence_fact(
                pattern_condition, subject, sequence_fact
            )
    if branch is None or branch.pattern is None:
        return None

    guard_components = [
        component
        for component in guard_components
        if not is_redundant_union_sequence_type_guard(component, subject, branch.facts)
    ]

    return BranchFacts(
        condition=condition,
        subject=subject,
        facts=branch.facts,
        pattern=branch.pattern,
        guard=combine_guards(guard_components),
    )


def is_redundant_union_sequence_type_guard(
    component: cst.BaseExpression,
    subject: cst.BaseExpression,
    facts: tuple[BranchFact, ...],
) -> bool:
    sequence_path = extract_list_tuple_isinstance_path(component, subject)
    if sequence_path is None:
        return False
    return any(
        isinstance(fact, ClassFact)
        and len(fact.classes) > 1
        and sequence_path.starts_with(fact.path)
        and len(sequence_path.parts) > len(fact.path.parts)
        for fact in facts
    )


def is_fact_backed_pattern_component(
    component: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> bool:
    or_branch = normalize_or_branch_facts(component, subject, ignore_types_pattern)
    if or_branch is not None and or_branch.guard is None:
        return True

    sequence_fact = normalize_sequence_length_fact(component, subject)
    if sequence_fact is not None:
        return True

    value_fact = normalize_value_fact(component, subject)
    if value_fact is not None:
        return is_fact_pattern_path(value_fact.path)

    class_fact = normalize_class_fact(component, subject, ignore_types_pattern)
    if extract_list_tuple_isinstance_path(component, subject) is not None:
        return False
    if class_fact is not None:
        return is_fact_pattern_path(class_fact.path)

    or_fact = normalize_path_or_fact(component, subject, ignore_types_pattern)
    if or_fact is not None:
        return is_fact_pattern_path(or_fact.path)

    return False


def is_fact_pattern_path(path: SubjectPath) -> bool:
    return (
        path.is_subject
        or path.attribute_names is not None
        or path.starts_with_subscript
        or sequence_element_parent(path) is not None
    )


def is_allowed_subject_guard(
    component: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    return extract_list_tuple_isinstance_path(
        component, subject
    ) is not None or is_sequence_subject_guard_component(component, subject)


def is_derived_fact_pattern_path(path: SubjectPath) -> bool:
    return not path.is_subject and is_fact_pattern_path(path)


def contains_subject_path(node: cst.CSTNode, subject: cst.BaseExpression) -> bool:
    if isinstance(node, cst.BaseExpression):
        path = SubjectPath.from_expression(node, subject)
        if path is not None:
            return True
    return any(contains_subject_path(child, subject) for child in node.children)


def normalize_subject_value_fact(
    condition: cst.BaseExpression, subject: cst.BaseExpression
) -> ValueFact | None:
    value_fact = normalize_value_fact(condition, subject)
    if value_fact is None or not value_fact.path.is_subject:
        return None
    return value_fact


def append_unique_fact(
    facts: list[PathFact],
    fact: PathFact,
    seen_paths: set[SubjectPath],
) -> bool:
    if fact.path in seen_paths:
        return False
    seen_paths.add(fact.path)
    facts.append(fact)
    return True


def normalize_value_fact(
    condition: cst.BaseExpression, subject: cst.BaseExpression
) -> ValueFact | None:
    if not isinstance(condition, cst.Comparison) or len(condition.comparisons) != 1:
        return None
    path = SubjectPath.from_expression(condition.left, subject)
    if path is None:
        return None

    target = condition.comparisons[0]
    if isinstance(target.operator, cst.Is):
        if not is_singleton_name(target.comparator):
            return None
        return ValueFact(path, target.comparator)
    if isinstance(target.operator, cst.Equal) and is_literal_value(target.comparator):
        return ValueFact(path, target.comparator)
    return None


def normalize_subject_class_fact(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> ClassFact | None:
    class_fact = normalize_class_fact(condition, subject, ignore_types_pattern)
    if class_fact is None or not class_fact.path.is_subject:
        return None
    return class_fact


def normalize_class_fact(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> ClassFact | None:
    if not isinstance(condition, cst.Call) or not m.matches(
        condition, m.Call(func=m.Name(value="isinstance"))
    ):
        return None
    if len(condition.args) < 2:
        return None
    path = SubjectPath.from_expression(condition.args[0].value, subject)
    if path is None:
        return None
    class_exprs = extract_isinstance_classes(
        condition.args[1].value, ignore_types_pattern
    )
    if class_exprs is None:
        return None
    return ClassFact(path, tuple(class_exprs))


def normalize_path_or_fact(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> OrFact | None:
    parts = flatten_boolean(condition, cst.Or)
    if len(parts) <= 1:
        return None

    path: SubjectPath | None = None
    alternatives: list[ValueFact | ClassFact | PatternTree] = []
    for part in parts:
        part = remove_redundant_subject_checks(
            part, subject, remove_sequence_type_checks=True
        )
        fact = normalize_value_fact(part, subject)
        if fact is None:
            fact = normalize_class_fact(part, subject, ignore_types_pattern)
        if fact is None:
            pattern_info = normalize_path_pattern_tree(
                part, subject, ignore_types_pattern
            )
            if pattern_info is None:
                pattern_info = normalize_path_sequence_pattern_tree(
                    part, subject, ignore_types_pattern
                )
            if pattern_info is None:
                return None
            fact_path, pattern_tree = pattern_info
            if path is None:
                path = fact_path
            elif fact_path != path:
                return None
            alternatives.append(pattern_tree)
            continue
        if path is None:
            path = fact.path
        elif fact.path != path:
            return None
        alternatives.append(fact)

    if path is None:
        return None
    return OrFact(path, tuple(alternatives))


def normalize_path_pattern_tree(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> tuple[SubjectPath, PatternTree] | None:
    if not isinstance(condition, cst.BooleanOperation) or not isinstance(
        condition.operator, cst.And
    ):
        return None

    class_fact: ClassFact | None = None
    value_facts: list[ValueFact] = []
    class_facts: list[ClassFact] = []
    sequence_facts: list[SequenceFact] = []
    or_facts: list[OrFact] = []
    seen_paths: set[SubjectPath] = set()
    for component in flatten_boolean(condition, cst.And):
        component_class_fact = normalize_class_fact(
            component, subject, ignore_types_pattern
        )
        if component_class_fact is not None and class_fact is None:
            class_fact = component_class_fact
            seen_paths.add(component_class_fact.path)
            continue

        sequence_fact = normalize_sequence_length_fact(component, subject)
        if sequence_fact is not None:
            if not append_unique_fact(sequence_facts, sequence_fact, seen_paths):
                return None
            continue

        or_fact = normalize_path_or_fact(component, subject, ignore_types_pattern)
        if or_fact is not None:
            if not append_unique_fact(or_facts, or_fact, seen_paths):
                return None
            continue

        component_class_fact = normalize_class_fact(
            component, subject, ignore_types_pattern
        )
        if component_class_fact is not None:
            if not append_unique_fact(class_facts, component_class_fact, seen_paths):
                return None
            continue

        value_fact = normalize_value_fact(component, subject)
        if value_fact is not None:
            if not append_unique_fact(value_facts, value_fact, seen_paths):
                return None
            continue

        return None

    if class_fact is None or not (
        value_facts or class_facts or sequence_facts or or_facts
    ):
        return None

    base_path = class_fact.path
    if not all(
        fact_path_starts_with(fact.path, base_path)
        for fact in (*value_facts, *class_facts, *sequence_facts, *or_facts)
    ):
        return None

    return (
        base_path,
        PatternTree.from_class_fact(
            ClassFact(SubjectPath(()), class_fact.classes),
            value_facts=strip_path_prefix(base_path, tuple(value_facts)),
            class_facts=strip_path_prefix(base_path, tuple(class_facts)),
            sequence_facts=strip_path_prefix(base_path, tuple(sequence_facts)),
            or_facts=strip_path_prefix(base_path, tuple(or_facts)),
        ),
    )


def normalize_path_sequence_pattern_tree(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> tuple[SubjectPath, PatternTree] | None:
    sequence_facts = normalize_sequence_pattern_facts(
        condition, subject, ignore_types_pattern
    )
    if sequence_facts is None:
        return None

    (
        sequence_fact,
        value_facts,
        class_facts,
        nested_sequence_facts,
        or_facts,
    ) = sequence_facts
    base_path = sequence_fact.path
    return (
        base_path,
        PatternTree.from_sequence_fact(
            SequenceFact(SubjectPath(()), sequence_fact.length, sequence_fact.use_star),
            value_facts=strip_path_prefix(base_path, value_facts),
            class_facts=strip_path_prefix(base_path, class_facts),
            sequence_facts=strip_path_prefix(base_path, nested_sequence_facts),
            or_facts=strip_path_prefix(base_path, or_facts),
        ),
    )


def fact_path_starts_with(path: SubjectPath, prefix: SubjectPath) -> bool:
    return len(path.parts) > len(prefix.parts) and path.starts_with(prefix)


def strip_path_prefix(
    prefix: SubjectPath,
    facts: tuple[PathFact, ...],
) -> tuple[PathFact, ...]:
    stripped: list[PathFact] = []
    for fact in facts:
        path = fact.path.strip_prefix(prefix)
        stripped.append(replace_fact_path(fact, path))
    return tuple(stripped)


def normalize_subject_class_attribute_facts(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> (
    tuple[
        ClassFact,
        tuple[ValueFact, ...],
        tuple[ClassFact, ...],
        tuple[SequenceFact, ...],
        tuple[OrFact, ...],
    ]
    | None
):
    if not isinstance(condition, cst.BooleanOperation) or not isinstance(
        condition.operator, cst.And
    ):
        return None

    class_fact: ClassFact | None = None
    value_facts: list[ValueFact] = []
    attribute_class_facts: list[ClassFact] = []
    attribute_sequence_facts: list[SequenceFact] = []
    attribute_or_facts: list[OrFact] = []
    seen_paths: set[SubjectPath] = set()
    for component in flatten_boolean(condition, cst.And):
        component_class_fact = normalize_subject_class_fact(
            component, subject, ignore_types_pattern
        )
        if component_class_fact is not None:
            if class_fact is not None:
                return None
            class_fact = component_class_fact
            continue

        sequence_fact = normalize_sequence_length_fact(component, subject)
        if sequence_fact is not None and not sequence_fact.path.is_subject:
            if not append_unique_fact(
                attribute_sequence_facts, sequence_fact, seen_paths
            ):
                return None
            continue

        or_fact = normalize_path_or_fact(component, subject, ignore_types_pattern)
        if or_fact is not None and is_derived_fact_pattern_path(or_fact.path):
            if not append_unique_fact(attribute_or_facts, or_fact, seen_paths):
                return None
            continue

        attribute_class_fact = normalize_class_fact(
            component, subject, ignore_types_pattern
        )
        if attribute_class_fact is not None and is_derived_fact_pattern_path(
            attribute_class_fact.path
        ):
            if not append_unique_fact(
                attribute_class_facts, attribute_class_fact, seen_paths
            ):
                return None
            continue

        value_fact = normalize_value_fact(component, subject)
        if value_fact is not None and is_derived_fact_pattern_path(value_fact.path):
            if not append_unique_fact(value_facts, value_fact, seen_paths):
                return None
            continue

        return None

    if class_fact is None or not (
        value_facts
        or attribute_class_facts
        or attribute_sequence_facts
        or attribute_or_facts
    ):
        return None
    if not validate_attribute_fact_paths(
        tuple(value_facts),
        tuple(attribute_class_facts),
        tuple(attribute_sequence_facts),
        tuple(attribute_or_facts),
    ):
        return None
    return (
        class_fact,
        tuple(value_facts),
        tuple(attribute_class_facts),
        tuple(attribute_sequence_facts),
        tuple(attribute_or_facts),
    )


def validate_attribute_fact_paths(
    value_facts: tuple[ValueFact, ...],
    class_facts: tuple[ClassFact, ...],
    sequence_facts: tuple[SequenceFact, ...],
    or_facts: tuple[OrFact, ...],
) -> bool:
    class_paths = {
        names
        for fact in class_facts
        for names in (fact.path.attribute_names,)
        if names is not None
    }
    class_subject_paths = {fact.path for fact in class_facts}
    sequence_paths = {fact.path for fact in sequence_facts}
    all_attribute_paths = [
        names
        for fact in (*value_facts, *class_facts, *sequence_facts, *or_facts)
        for names in (fact.path.attribute_names,)
        if names is not None
    ]

    for path in all_attribute_paths:
        if not path:
            return False
        if len(path) > 1 and path[:-1] not in class_paths:
            return False
    for fact in (*value_facts, *class_facts, *or_facts):
        sequence_parent = sequence_element_parent(fact.path)
        if sequence_parent is not None and not has_sequence_or_class_parent(
            fact.path, sequence_paths, class_subject_paths
        ):
            return False
    for value_fact in value_facts:
        value_path = value_fact.path.attribute_names
        if value_path in class_paths:
            return False
        if value_fact.path in sequence_paths:
            return False
    for class_fact in class_facts:
        if class_fact.path in sequence_paths:
            return False
    for or_fact in or_facts:
        or_path = or_fact.path.attribute_names
        if or_path in class_paths:
            return False
        if or_fact.path in sequence_paths:
            return False
    for sequence_fact in sequence_facts:
        names = sequence_fact.path.attribute_names
        if names is None and has_sequence_or_class_parent(
            sequence_fact.path, sequence_paths, class_subject_paths
        ):
            continue
        if names is None:
            return False
        if len(names) > 1 and names[:-1] not in class_paths:
            return False
        element_indices = sequence_element_indices_for_path(
            sequence_fact.path, value_facts, class_facts, sequence_facts, or_facts
        )
        if (
            not sequence_fact.use_star
            and element_indices
            and max(element_indices) >= sequence_fact.length
        ):
            return False
        if not sequence_fact.use_star and not validate_wildcard_constraint(
            {index: WildcardElementPattern() for index in element_indices},
            sequence_fact.length,
        ):
            return False
    return True


def normalize_sequence_length_fact(
    condition: cst.BaseExpression, subject: cst.BaseExpression
) -> SequenceFact | None:
    length = extract_subject_sequence_length(condition, subject)
    if length is None:
        return None
    len_call = condition.left  # type: ignore[assignment]
    path = SubjectPath.from_expression(len_call.args[0].value, subject)
    if path is None:
        return None
    use_star = isinstance(condition.comparisons[0].operator, cst.GreaterThanEqual)
    return SequenceFact(path, length, use_star=use_star)


def normalize_sequence_pattern_facts(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> (
    tuple[
        SequenceFact,
        tuple[ValueFact, ...],
        tuple[ClassFact, ...],
        tuple[SequenceFact, ...],
        tuple[OrFact, ...],
    ]
    | None
):
    if not isinstance(condition, cst.BooleanOperation) or not isinstance(
        condition.operator, cst.And
    ):
        return None

    value_facts: list[ValueFact] = []
    class_facts: list[ClassFact] = []
    sequence_facts: list[SequenceFact] = []
    or_facts: list[OrFact] = []
    seen_paths: set[SubjectPath] = set()
    for component in flatten_boolean(condition, cst.And):
        component_sequence_fact = normalize_sequence_length_fact(component, subject)
        if component_sequence_fact is not None:
            if not append_unique_fact(
                sequence_facts, component_sequence_fact, seen_paths
            ):
                return None
            continue

        value_fact = normalize_value_fact(component, subject)
        if value_fact is not None:
            if not append_unique_fact(value_facts, value_fact, seen_paths):
                return None
            continue

        class_fact = normalize_class_fact(component, subject, ignore_types_pattern)
        if class_fact is not None:
            if not append_unique_fact(class_facts, class_fact, seen_paths):
                return None
            continue

        or_fact = normalize_path_or_fact(component, subject, ignore_types_pattern)
        if or_fact is not None:
            if not append_unique_fact(or_facts, or_fact, seen_paths):
                return None
            continue

        return None

    if not sequence_facts:
        return None

    sequence_fact: SequenceFact | None = None
    nested_sequence_facts: tuple[SequenceFact, ...] = ()
    for candidate in sorted(sequence_facts, key=lambda fact: len(fact.path.parts)):
        candidate_nested_sequence_facts = tuple(
            fact for fact in sequence_facts if fact != candidate
        )
        if not (
            value_facts or class_facts or candidate_nested_sequence_facts or or_facts
        ):
            continue
        if not all(
            fact_path_starts_with(fact.path, candidate.path)
            for fact in (
                *value_facts,
                *class_facts,
                *candidate_nested_sequence_facts,
                *or_facts,
            )
        ):
            continue
        sequence_fact = candidate
        nested_sequence_facts = candidate_nested_sequence_facts
        break

    if sequence_fact is None:
        return None
    if not validate_sequence_fact_paths(
        sequence_fact,
        tuple(value_facts),
        tuple(class_facts),
        nested_sequence_facts,
        tuple(or_facts),
    ):
        return None
    return (
        sequence_fact,
        tuple(value_facts),
        tuple(class_facts),
        nested_sequence_facts,
        tuple(or_facts),
    )


def sequence_element_parent(path: SubjectPath) -> SubjectPath | None:
    if not isinstance(path.last_part, SubscriptPathPart):
        return None
    if path.last_part.index is None:
        return None
    return path.parent()


def sequence_element_indices_for_path(
    sequence_path: SubjectPath,
    value_facts: tuple[ValueFact, ...],
    class_facts: tuple[ClassFact, ...],
    sequence_facts: tuple[SequenceFact, ...],
    or_facts: tuple[OrFact, ...],
) -> set[int]:
    indices: set[int] = set()
    for fact in (*value_facts, *class_facts, *sequence_facts, *or_facts):
        if sequence_element_parent(fact.path) != sequence_path:
            continue
        index = direct_sequence_index(fact.path.strip_prefix(sequence_path))
        if index is not None:
            indices.add(index)
    return indices


def normalize_subject_sequence_facts(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> (
    tuple[
        SequenceFact,
        tuple[ValueFact, ...],
        tuple[ClassFact, ...],
        tuple[SequenceFact, ...],
        tuple[OrFact, ...],
    ]
    | None
):
    sequence_facts = normalize_sequence_pattern_facts(
        condition, subject, ignore_types_pattern
    )
    if sequence_facts is None:
        return None
    if not sequence_facts[0].path.is_subject:
        return None
    return sequence_facts


def validate_sequence_fact_paths(
    root_sequence: SequenceFact,
    value_facts: tuple[ValueFact, ...],
    class_facts: tuple[ClassFact, ...],
    sequence_facts: tuple[SequenceFact, ...],
    or_facts: tuple[OrFact, ...],
) -> bool:
    sequence_by_path = {
        root_sequence.path: root_sequence,
        **{fact.path: fact for fact in sequence_facts},
    }
    class_paths = {fact.path for fact in class_facts}
    for fact in sequence_facts:
        if not has_sequence_or_class_parent(
            fact.path, set(sequence_by_path), class_paths
        ):
            return False

    for fact in (*value_facts, *class_facts, *or_facts):
        if not has_sequence_or_class_parent(
            fact.path, set(sequence_by_path), class_paths
        ):
            return False

    for sequence in sequence_by_path.values():
        element_indices = sequence_element_indices_for_path(
            sequence.path, value_facts, class_facts, sequence_facts, or_facts
        )
        if (
            not sequence.use_star
            and element_indices
            and max(element_indices) >= sequence.length
        ):
            return False
        if not sequence.use_star and not validate_wildcard_constraint(
            {index: WildcardElementPattern() for index in element_indices},
            sequence.length,
        ):
            return False
    return True


def is_under_class_path(path: SubjectPath, class_paths: set[SubjectPath]) -> bool:
    return any(
        path.starts_with(class_path) and len(path.parts) > len(class_path.parts)
        for class_path in class_paths
    )


def has_sequence_or_class_parent(
    path: SubjectPath,
    sequence_paths: set[SubjectPath],
    class_paths: set[SubjectPath],
) -> bool:
    parent = sequence_element_parent(path)
    return (
        parent in sequence_paths
        or parent in class_paths
        or is_under_class_path(path, class_paths)
    )


def extract_subject_sequence_length(
    condition: cst.BaseExpression, subject: cst.BaseExpression
) -> int | None:
    if not isinstance(condition, cst.Comparison) or len(condition.comparisons) != 1:
        return None
    target = condition.comparisons[0]
    if not isinstance(target.operator, (cst.Equal, cst.GreaterThanEqual)):
        return None
    if not isinstance(target.comparator, cst.Integer):
        return None
    if not isinstance(condition.left, cst.Call) or not m.matches(
        condition.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])
    ):
        return None
    if len(condition.left.args) != 1:
        return None
    if SubjectPath.from_expression(condition.left.args[0].value, subject) is None:
        return None
    return int(target.comparator.value)


def direct_sequence_index(path: SubjectPath) -> int | None:
    if len(path.parts) != 1 or not isinstance(path.first_part, SubscriptPathPart):
        return None
    return path.first_part.index


def extract_attribute_literal_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[str, cst.BaseExpression] | None:
    if not m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget()])):
        return None
    comparison = node  # type: ignore[assignment]
    if len(comparison.comparisons) != 1 or not isinstance(
        comparison.left, cst.Attribute
    ):
        return None
    path = SubjectPath.from_expression(comparison.left, subject)
    if path is None:
        return None
    attr_name = path.direct_attribute_name
    if attr_name is None:
        return None

    target = comparison.comparisons[0]
    if isinstance(target.operator, cst.Is) and not is_singleton_name(target.comparator):
        return None
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return None
    if not is_literal_value(target.comparator):
        return None

    return attr_name, target.comparator


def contains_subscript(node: cst.CSTNode) -> bool:
    if isinstance(node, cst.Subscript):
        return True
    return any(contains_subscript(child) for child in node.children)
