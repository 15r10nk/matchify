"""Recognizers that turn branch conditions into match patterns and guards."""

from __future__ import annotations

import libcst as cst
from libcst import matchers as m

from .patterns import (
    ClassPatternPart,
    PatternMatch,
    PatternPart,
    ValuePatternPart,
    build_class_pattern,
    build_or_pattern,
    build_pattern_from_parts,
    build_value_pattern,
    combine_guards,
    extract_isinstance_call,
    extract_isinstance_classes,
    flatten_boolean,
    is_literal_value,
    is_singleton_name,
)
from .safety import is_safe_condition
from .sequence_patterns import (
    ClassElementPattern,
    NestedSequenceElementPattern,
    RawElementPattern,
    SequencePatternCollector,
    WildcardElementPattern,
    build_bracketed_sequence_match_list,
    build_sequence_element_class_pattern,
    build_sequence_match_list,
    extract_len_sequence_attribute,
    extract_nested_sequence_element,
    extract_sequence_element_direct_attribute_check,
    extract_sequence_pattern_for_subject,
    find_sequence_subject,
    is_component_for_sequence_subject,
    is_sequence_attribute_component,
    validate_wildcard_constraint,
)
from .subject_path import AttributePathPart, SubjectPath, SubjectPathPart


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


class BranchPatternRecognizer:
    """Base class for branch condition recognizers."""

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        raise NotImplementedError


class EqualityPatternRecognizer(BranchPatternRecognizer):
    """Recognizes `subject == literal` and `subject is singleton` branches."""

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        if not m.matches(condition, m.Comparison(comparisons=[m.ComparisonTarget()])):
            return None

        comparison = condition  # type: ignore[assignment]
        if len(comparison.comparisons) != 1 or not comparison.left.deep_equals(subject):
            return None

        target = comparison.comparisons[0]
        if isinstance(target.operator, cst.Is):
            if not is_singleton_name(target.comparator):
                return None
            return PatternMatch(build_value_pattern(target.comparator), None)

        if isinstance(target.operator, cst.Equal) and is_literal_value(
            target.comparator
        ):
            return PatternMatch(build_value_pattern(target.comparator), None)

        return None


class OrPatternRecognizer(BranchPatternRecognizer):
    """Recognizes OR chains of value or plain class patterns."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        parts = flatten_boolean(condition, cst.Or)
        if len(parts) <= 1:
            return None

        patterns = []
        for part in parts:
            pattern = self._recognize_part_pattern(part, subject)
            if pattern is None:
                return None
            extend_or_patterns(patterns, pattern)

        return PatternMatch(build_or_pattern(patterns), None)

    def _recognize_part_pattern(
        self, part: cst.BaseExpression, subject: cst.BaseExpression
    ) -> cst.MatchPattern | None:
        part = remove_redundant_hasattr_checks(part, subject)

        result = EqualityPatternRecognizer().recognize(part, subject)
        if result is not None and result.guard is None:
            return result.pattern

        class_exprs = extract_isinstance_call(
            part, subject, ignore_types_pattern=self.ignore_types_pattern
        )
        if class_exprs is not None:
            return build_class_pattern(class_exprs)

        if not isinstance(part, cst.BooleanOperation) or not isinstance(
            part.operator, cst.And
        ):
            return None

        for recognizer in (
            ClassPatternRecognizer(self.ignore_types_pattern),
            SequencePatternRecognizer(),
            NestedClassPatternRecognizer(self.ignore_types_pattern),
            SequenceAttributePatternRecognizer(self.ignore_types_pattern),
        ):
            part_result = recognizer.recognize(part, subject)
            if (
                part_result is not None
                and part_result.guard is None
                and part_result.pattern is not None
            ):
                if isinstance(part_result.pattern, cst.MatchList):
                    return part_result.pattern.with_changes(
                        lbracket=cst.LeftSquareBracket(),
                        rbracket=cst.RightSquareBracket(),
                    )
                return part_result.pattern

        return None


def extend_or_patterns(
    patterns: list[cst.MatchPattern], pattern: cst.MatchPattern
) -> None:
    if isinstance(pattern, cst.MatchOr):
        patterns.extend(element.pattern for element in pattern.patterns)
        return
    patterns.append(pattern)


def remove_redundant_hasattr_checks(
    part: cst.BaseExpression, subject: cst.BaseExpression
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
        if extract_hasattr_attribute_path(component, subject) not in checked_paths
    ]
    if len(filtered) == len(components):
        return part
    if len(filtered) == 1:
        return filtered[0]
    combined = combine_guards(filtered)
    return combined if combined is not None else part


def collect_checked_attribute_paths(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> set[tuple[SubjectPathPart, ...]]:
    if isinstance(node, cst.BooleanOperation) and isinstance(node.operator, cst.Or):
        parts = [
            collect_checked_attribute_paths(part, subject)
            for part in flatten_boolean(node, cst.Or)
        ]
        merged = set().union(*parts)
        return merged if len(merged) == 1 else set()

    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return set()

    path = SubjectPath.from_expression(node.left, subject)
    if (
        path is None
        or not path.parts
        or not isinstance(path.parts[-1], AttributePathPart)
    ):
        return set()

    target = node.comparisons[0]
    if isinstance(target.operator, cst.Is) and not is_singleton_name(target.comparator):
        return set()
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return set()
    if not is_literal_value(target.comparator):
        return set()

    return {path.parts}


def extract_hasattr_attribute_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[SubjectPathPart, ...] | None:
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
    return path.parts + (AttributePathPart(literal),)


class ClassPatternRecognizer(BranchPatternRecognizer):
    """Recognizes simple isinstance/class-attribute branches."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        components = flatten_boolean(condition, cst.And)
        class_exprs: list[cst.BaseExpression] | None = None
        attrs: list[tuple[str, cst.MatchPattern]] = []
        guards: list[cst.BaseExpression] = []

        for component in components:
            isinstance_info = extract_isinstance_call(
                component, subject, self.ignore_types_pattern
            )
            if isinstance_info is not None:
                if class_exprs is not None:
                    guards.append(component)
                    continue
                class_exprs = isinstance_info
                continue

            if (
                extract_len_sequence_attribute(component, subject) is not None
                or extract_attribute_path_sequence_len_check(component, subject)
                is not None
            ):
                return None

            if is_subject_derived_complex_pattern(component, subject):
                return None

            attr_check = extract_attribute_pattern_check(component, subject)
            if attr_check is not None:
                attrs.append(attr_check)
                continue

            guards.append(component)

        if class_exprs is None:
            return None

        pattern = build_class_pattern(class_exprs, attrs)

        return PatternMatch(pattern, combine_guards(guards))


class SequencePatternRecognizer(BranchPatternRecognizer):
    """Recognizes top-level sequence patterns from len/index checks."""

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        if find_sequence_subject(condition) is None:
            return None

        collector = SequencePatternCollector(subject)
        components = flatten_boolean(condition, cst.And)
        guards: list[cst.BaseExpression] = []
        for component in components:
            if self._is_sequence_pattern_component(component, collector):
                if not collector.collect_from_node(component):
                    return None
                continue
            if is_component_for_sequence_subject(component, subject):
                if self._is_sequence_guard_component(component, subject):
                    guards.append(component)
                continue

            guards.append(component)

        for component in components:
            attr_check = extract_sequence_element_direct_attribute_check(
                component, subject
            )
            if attr_check is None:
                continue
            index, _, _ = attr_check
            if not isinstance(collector.elements.get(index), ClassElementPattern):
                return None

        for index in collector.nested_sequences:
            nested_result = extract_nested_sequence_element(condition, subject, index)
            if nested_result is None:
                return None
            pattern_infos, use_star = nested_result
            collector.elements[index] = NestedSequenceElementPattern(
                pattern_infos, use_star
            )

        if collector.expected_len is not None:
            required_len = collector.expected_len
            use_star = False
        elif collector.min_len is not None:
            required_len = collector.min_len
            use_star = collector.use_star_pattern
        else:
            return None

        if not collector.elements and not guards:
            return None
        if not collector.elements and use_star:
            return None
        if not use_star:
            if collector.elements and max(collector.elements) >= required_len:
                return None
            if not validate_wildcard_constraint(collector.elements, required_len):
                return None

        pattern_infos = []
        for index in range(required_len):
            pattern_info = collector.elements.get(index, WildcardElementPattern())
            if isinstance(pattern_info, ClassElementPattern):
                element_subject = cst.Subscript(
                    value=subject,
                    slice=[
                        cst.SubscriptElement(
                            slice=cst.Index(value=cst.Integer(str(index)))
                        )
                    ],
                )
                nested_pattern = build_sequence_element_class_pattern(
                    condition, element_subject, pattern_info.classes
                )
                if nested_pattern is not None:
                    pattern_info = RawElementPattern(nested_pattern)
            pattern_infos.append(pattern_info)
        return PatternMatch(
            build_sequence_match_list(pattern_infos, use_star),
            combine_guards(guards),
        )

    def _is_sequence_pattern_component(
        self, component: cst.BaseExpression, collector: SequencePatternCollector
    ) -> bool:
        return (
            collector._is_len_check(component)
            or collector._is_subscript_literal_check(component)
            or collector._extract_subscript_or_pattern(component) is not None
            or collector._is_subscript_isinstance_check(component)
            or collector._is_nested_len_check(component)
            or collector._is_nested_subscript_check(component)
            or extract_sequence_element_direct_attribute_check(
                component, collector.subject
            )
            is not None
        )

    def _is_sequence_guard_component(
        self, component: cst.BaseExpression, subject: cst.BaseExpression
    ) -> bool:
        return is_sequence_subject_guard_component(component, subject)


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


class NestedClassPatternRecognizer(BranchPatternRecognizer):
    """Recognizes nested isinstance checks on attribute paths."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        components = flatten_boolean(condition, cst.And)
        main_classes: list[cst.BaseExpression] | None = None
        nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]] = {}
        scalar_checks: dict[tuple[str, ...], cst.MatchPattern] = {}
        sequence_checks: dict[tuple[str, ...], cst.BaseExpression] = {}
        guards: list[cst.BaseExpression] = []

        for component in components:
            if isinstance(component, cst.Call) and m.matches(
                component, m.Call(func=m.Name(value="isinstance"))
            ):
                if len(component.args) < 2:
                    return None
                class_exprs = extract_isinstance_classes(
                    component.args[1].value, self.ignore_types_pattern
                )
                if class_exprs is None:
                    return None
                arg = component.args[0].value
                if arg.deep_equals(subject):
                    if main_classes is None:
                        main_classes = class_exprs
                    else:
                        guards.append(component)
                    continue
                path = SubjectPath.from_expression(arg, subject)
                attr_path = path.attribute_names if path is not None else None
                if attr_path is None:
                    if any(
                        is_component_for_sequence_subject(component, sequence_subject)
                        for sequence_subject in sequence_checks.values()
                    ):
                        continue
                    guards.append(component)
                    continue
                nested_classes[attr_path] = class_exprs
                continue

            attr_check = extract_attribute_path_pattern_check(component, subject)
            if attr_check is not None:
                path, pattern = attr_check
                scalar_checks[path] = pattern
                continue

            attr_guard = extract_attribute_path_guard_check(component, subject)
            if attr_guard is not None:
                guards.append(attr_guard)
                continue

            sequence_check = extract_attribute_path_sequence_len_check(
                component, subject
            )
            if sequence_check is not None:
                path, sequence_subject = sequence_check
                sequence_checks[path] = sequence_subject
                continue

            if any(
                is_component_for_sequence_subject(component, sequence_subject)
                for sequence_subject in sequence_checks.values()
            ):
                if any(
                    is_sequence_subject_guard_component(component, sequence_subject)
                    for sequence_subject in sequence_checks.values()
                ):
                    guards.append(component)
                continue

            if is_subject_derived_complex_pattern(component, subject):
                return None

            guards.append(component)

        if any(path in nested_classes for path in sequence_checks):
            return None

        if main_classes is None or not nested_classes:
            return None

        patterns: list[cst.MatchPattern] = []
        for class_expr in main_classes:
            pattern = build_nested_class_pattern(
                condition,
                class_expr,
                (),
                nested_classes,
                scalar_checks,
                sequence_checks,
            )
            if pattern is None:
                return None
            patterns.append(pattern)
        return PatternMatch(build_or_pattern(patterns), combine_guards(guards))


class SequenceAttributePatternRecognizer(BranchPatternRecognizer):
    """Recognizes class patterns with sequence-valued attributes."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        components = flatten_boolean(condition, cst.And)
        class_exprs: list[cst.BaseExpression] | None = None
        sequence_subjects: dict[str, cst.Attribute] = {}
        scalar_attrs: list[tuple[str, cst.MatchPattern]] = []
        nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]] = {}
        nested_class_components: dict[tuple[str, ...], cst.BaseExpression] = {}
        nested_scalar_checks: dict[tuple[str, ...], cst.MatchPattern] = {}
        nested_sequence_checks: dict[tuple[str, ...], cst.BaseExpression] = {}
        guards: list[cst.BaseExpression] = []

        for component in components:
            isinstance_info = extract_isinstance_call(
                component, subject, self.ignore_types_pattern
            )
            if isinstance_info is not None:
                if class_exprs is None:
                    class_exprs = isinstance_info
                else:
                    guards.append(component)
                continue

            nested_isinstance = extract_attribute_path_isinstance_check(
                component, subject, self.ignore_types_pattern
            )
            if nested_isinstance is not None:
                path, classes = nested_isinstance
                nested_classes[path] = classes
                nested_class_components[path] = component
                continue

            sequence_subject = extract_len_sequence_attribute(component, subject)
            if sequence_subject is not None:
                sequence_subjects[sequence_subject.attr.value] = sequence_subject
                continue

            nested_sequence_check = extract_attribute_path_sequence_len_check(
                component, subject
            )
            if nested_sequence_check is not None:
                path, sequence_subject = nested_sequence_check
                nested_sequence_checks[path] = sequence_subject
                continue

            attr_check = extract_attribute_pattern_check(component, subject)
            if attr_check is not None:
                scalar_attrs.append(attr_check)
                continue

            nested_scalar_check = extract_attribute_path_pattern_check(
                component, subject
            )
            if nested_scalar_check is not None:
                path, pattern = nested_scalar_check
                nested_scalar_checks[path] = pattern
                continue

            attr_guard = extract_attribute_path_guard_check(component, subject)
            if attr_guard is not None:
                guards.append(attr_guard)
                continue

            if is_hasattr_guard(component, subject):
                guards.append(component)
                continue

            sequence_guard_subjects = list(sequence_subjects.values()) + list(
                nested_sequence_checks.values()
            )
            if any(
                is_component_for_sequence_subject(component, sequence_subject)
                for sequence_subject in sequence_guard_subjects
            ):
                if any(
                    is_sequence_subject_guard_component(component, sequence_subject)
                    for sequence_subject in sequence_guard_subjects
                ):
                    guards.append(component)
                continue

            if is_sequence_attribute_component(component, subject):
                continue

            if is_subject_derived_complex_pattern(component, subject):
                return None

            guards.append(component)

        if class_exprs is None or not (sequence_subjects or nested_sequence_checks):
            return None

        keyword_patterns: list[tuple[str, cst.MatchPattern]] = []
        used_attrs: set[str] = set()
        for attr_name, sequence_subject in sequence_subjects.items():
            sequence_result = extract_sequence_pattern_for_subject(
                condition, sequence_subject
            )
            if sequence_result is None:
                return None
            pattern_infos, use_star = sequence_result
            keyword_patterns.append(
                (
                    attr_name,
                    build_bracketed_sequence_match_list(pattern_infos, use_star),
                )
            )
            used_attrs.add(attr_name)

        sequence_paths = {(attr_name,) for attr_name in sequence_subjects}
        sequence_paths.update(nested_sequence_checks)
        for path, component in nested_class_components.items():
            if path in sequence_paths:
                guards.append(component)
        for path in sequence_paths:
            nested_classes.pop(path, None)

        for attr_name, pattern in scalar_attrs:
            if attr_name in sequence_subjects:
                continue
            keyword_patterns.append((attr_name, pattern))
            used_attrs.add(attr_name)

        if nested_classes or nested_scalar_checks or nested_sequence_checks:
            nested_pattern = build_nested_class_pattern(
                condition,
                class_exprs[0],
                (),
                nested_classes,
                nested_scalar_checks,
                nested_sequence_checks,
            )
            if nested_pattern is None:
                return None
            for kwd in nested_pattern.kwds:
                if kwd.key.value in used_attrs:
                    continue
                keyword_patterns.append((kwd.key.value, kwd.pattern))
                used_attrs.add(kwd.key.value)

        return PatternMatch(
            build_class_pattern(class_exprs, keyword_patterns),
            combine_guards(guards),
        )


class GuardFallbackRecognizer(BranchPatternRecognizer):
    """Recognizes class/equality fragments in AND chains and preserves the rest."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def recognize(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch | None:
        if not is_safe_condition(condition, subject, self.ignore_types_pattern):
            return PatternMatch(None, condition)

        components = flatten_boolean(condition, cst.And)
        pattern_parts: list[PatternPart] = []
        attribute_checks = []
        guard_parts = []

        for component in components:
            or_pattern = OrPatternRecognizer(self.ignore_types_pattern).recognize(
                component, subject
            )
            if (
                or_pattern is not None
                and or_pattern.pattern is not None
                and or_pattern.guard is None
            ):
                pattern_parts.append(ValuePatternPart(or_pattern.pattern))
                continue

            equality = EqualityPatternRecognizer().recognize(component, subject)
            if equality is not None and equality.pattern is not None:
                pattern_parts.append(ValuePatternPart(equality.pattern))
                continue

            isinstance_info = extract_isinstance_call(
                component, subject, self.ignore_types_pattern
            )
            if isinstance_info is not None:
                pattern_parts.append(ClassPatternPart(isinstance_info))
                continue

            attr_check = extract_attribute_pattern_check(component, subject)
            if attr_check is not None:
                attribute_checks.append(attr_check)
                continue

            guard_parts.append(component)

        pattern = build_pattern_from_parts(pattern_parts, attribute_checks)
        guard = combine_guards(guard_parts)
        return PatternMatch(pattern, guard)


class PatternRecognitionEngine:
    """Runs branch recognizers in order, from specific to conservative."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern
        self.subject_recognizer = SubjectRecognizer(ignore_types_pattern)
        # Order matters: exact recognizers run before broader recognizers so the
        # fallback only preserves genuinely unsupported fragments as guards.
        self.branch_recognizers: list[BranchPatternRecognizer] = [
            OrPatternRecognizer(ignore_types_pattern),
            EqualityPatternRecognizer(),
            ClassPatternRecognizer(ignore_types_pattern),
            SequencePatternRecognizer(),
            NestedClassPatternRecognizer(ignore_types_pattern),
            SequenceAttributePatternRecognizer(ignore_types_pattern),
            GuardFallbackRecognizer(ignore_types_pattern),
        ]

    def recognize_subject(self, test: cst.BaseExpression) -> cst.BaseExpression | None:
        return self.subject_recognizer.recognize(test)

    def recognize_branch(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> PatternMatch:
        for recognizer in self.branch_recognizers:
            result = recognizer.recognize(condition, subject)
            if result is not None:
                return result
        return PatternMatch(None, condition)


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


def extract_attribute_pattern_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[str, cst.MatchPattern] | None:
    literal_check = extract_attribute_literal_check(node, subject)
    if literal_check is not None:
        attr_name, value = literal_check
        return attr_name, build_value_pattern(value)

    parts = flatten_boolean(node, cst.Or)
    if len(parts) <= 1:
        return None

    attr_name: str | None = None
    patterns: list[cst.MatchPattern] = []
    for part in parts:
        literal_part = extract_attribute_literal_check(part, subject)
        if literal_part is None:
            return None
        part_attr_name, value = literal_part
        if attr_name is None:
            attr_name = part_attr_name
        elif part_attr_name != attr_name:
            return None
        patterns.append(build_value_pattern(value))

    if attr_name is None:
        return None
    return attr_name, build_or_pattern(patterns)


def extract_attribute_path_literal_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[tuple[str, ...], cst.BaseExpression] | None:
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    path = SubjectPath.from_expression(node.left, subject)
    if path is None:
        return None
    attr_path = path.attribute_names
    if attr_path is None:
        return None

    target = node.comparisons[0]
    if isinstance(target.operator, cst.Is) and not is_singleton_name(target.comparator):
        return None
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return None
    if not is_literal_value(target.comparator):
        return None
    return attr_path, target.comparator


def extract_attribute_path_pattern_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[tuple[str, ...], cst.MatchPattern] | None:
    literal_check = extract_attribute_path_literal_check(node, subject)
    if literal_check is not None:
        path, value = literal_check
        return path, build_value_pattern(value)

    parts = flatten_boolean(node, cst.Or)
    if len(parts) <= 1:
        return None

    attr_path: tuple[str, ...] | None = None
    patterns: list[cst.MatchPattern] = []
    for part in parts:
        literal_part = extract_attribute_path_literal_check(part, subject)
        if literal_part is None:
            return None
        part_path, value = literal_part
        if attr_path is None:
            attr_path = part_path
        elif part_path != attr_path:
            return None
        patterns.append(build_value_pattern(value))

    if attr_path is None:
        return None
    return attr_path, build_or_pattern(patterns)


def extract_attribute_path_guard_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> cst.BaseExpression | None:
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None

    path = SubjectPath.from_expression(node.left, subject)
    if path is None or path.attribute_names is None:
        return None

    target = node.comparisons[0]
    if isinstance(target.operator, (cst.Equal, cst.Is)) and is_literal_value(
        target.comparator
    ):
        return None
    return node


def extract_attribute_path_isinstance_check(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    ignore_types_pattern: str | None,
) -> tuple[tuple[str, ...], list[cst.BaseExpression]] | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="isinstance"))
    ):
        return None
    if len(node.args) < 2:
        return None

    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:
        return None
    attr_path = path.attribute_names
    if attr_path is None:
        return None

    class_exprs = extract_isinstance_classes(node.args[1].value, ignore_types_pattern)
    if class_exprs is None:
        return None
    return attr_path, class_exprs


def extract_attribute_path_sequence_len_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[tuple[str, ...], cst.BaseExpression] | None:
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    if not isinstance(node.comparisons[0].operator, (cst.Equal, cst.GreaterThanEqual)):
        return None
    if not isinstance(node.comparisons[0].comparator, cst.Integer):
        return None
    if not m.matches(node.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
        return None

    len_call = node.left
    sequence_subject = len_call.args[0].value
    path = SubjectPath.from_expression(sequence_subject, subject)
    if path is None:
        return None
    attr_path = path.attribute_names
    if attr_path is None:
        return None
    return attr_path, sequence_subject


def is_hasattr_guard(node: cst.BaseExpression, subject: cst.BaseExpression) -> bool:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"))
    ):
        return False
    if len(node.args) != 2:
        return False
    checked_subject = node.args[0].value
    path = SubjectPath.from_expression(checked_subject, subject)
    return path is not None and (path.is_subject or path.attribute_names is not None)


def build_nested_class_pattern(
    condition: cst.BaseExpression,
    class_expr: cst.BaseExpression,
    path: tuple[str, ...],
    nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]],
    scalar_checks: dict[tuple[str, ...], cst.MatchPattern],
    sequence_checks: dict[tuple[str, ...], cst.BaseExpression],
) -> cst.MatchClass | None:
    child_names = {
        child_path[len(path)]
        for child_path in nested_classes
        if len(child_path) > len(path) and child_path[: len(path)] == path
    }
    scalar_names = {
        scalar_path[len(path)]
        for scalar_path in scalar_checks
        if len(scalar_path) == len(path) + 1 and scalar_path[: len(path)] == path
    }
    sequence_names = {
        sequence_path[len(path)]
        for sequence_path in sequence_checks
        if len(sequence_path) == len(path) + 1 and sequence_path[: len(path)] == path
    }

    kwds: list[cst.MatchKeywordElement] = []
    for name in sorted(
        child_names | scalar_names | sequence_names,
        key=lambda child_name: (0 if child_name in sequence_names else 1, child_name),
    ):
        child_path = path + (name,)
        if child_path in nested_classes:
            child_classes = nested_classes[child_path]
            child_patterns = []
            for child_class in child_classes:
                nested_child_pattern = build_nested_class_pattern(
                    condition,
                    child_class,
                    child_path,
                    nested_classes,
                    scalar_checks,
                    sequence_checks,
                )
                if nested_child_pattern is None:
                    return None
                child_patterns.append(nested_child_pattern)
            child_pattern: cst.MatchPattern = build_or_pattern(child_patterns)
        elif child_path in sequence_checks:
            sequence_result = extract_sequence_pattern_for_subject(
                condition, sequence_checks[child_path]
            )
            if sequence_result is None:
                return None
            pattern_infos, use_star = sequence_result
            child_pattern = build_bracketed_sequence_match_list(pattern_infos, use_star)
        else:
            child_pattern = scalar_checks[child_path]

        kwds.append(cst.MatchKeywordElement(key=cst.Name(name), pattern=child_pattern))

    return cst.MatchClass(cls=class_expr, patterns=[], kwds=kwds)


def is_subject_derived_complex_pattern(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    if isinstance(node, cst.Call) and m.matches(
        node, m.Call(func=m.Name(value="isinstance"))
    ):
        if len(node.args) >= 1:
            path = SubjectPath.from_expression(node.args[0].value, subject)
            return path is not None and not path.is_subject

    if isinstance(node, cst.Comparison):
        left = node.left
        if isinstance(left, cst.Call) and m.matches(
            left, m.Call(func=m.Name(value="len"))
        ):
            if (
                left.args
                and SubjectPath.from_expression(left.args[0].value, subject) is not None
            ):
                return True
        if (
            isinstance(left, cst.Subscript)
            and SubjectPath.from_expression(left, subject) is not None
        ):
            return True
        if isinstance(left, cst.Attribute):
            value_path = SubjectPath.from_expression(left.value, subject)
            return value_path is not None and not value_path.is_subject

    return False
