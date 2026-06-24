"""Sequence-pattern recognition and construction."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .patterns import (
    build_class_pattern,
    build_or_pattern,
    build_value_pattern,
    extract_isinstance_classes,
    flatten_boolean,
    is_literal_value,
    is_singleton_name,
)
from .subject_path import (
    AttributePathPart,
    SubjectPath,
    SubscriptPathPart,
    extract_integer_subscript_index,
)


@dataclass(frozen=True)
class LiteralElementPattern:
    """Sequence element known to match a literal or singleton value."""

    value: cst.BaseExpression


@dataclass(frozen=True)
class ClassElementPattern:
    """Sequence element known to match one or more classes."""

    classes: list[cst.BaseExpression]


@dataclass(frozen=True)
class WildcardElementPattern:
    """Sequence element with no constraint."""


@dataclass(frozen=True)
class NestedSequenceElementPattern:
    """Sequence element that is itself a bracketed sequence pattern."""

    elements: list[SequenceElementPattern]
    use_star: bool = False


@dataclass(frozen=True)
class RawElementPattern:
    """Already-built LibCST pattern used when another recognizer did the work."""

    pattern: cst.MatchPattern


SequenceElementPattern = (
    LiteralElementPattern
    | ClassElementPattern
    | WildcardElementPattern
    | NestedSequenceElementPattern
    | RawElementPattern
)


def extend_sequence_or_patterns(
    patterns: list[cst.MatchPattern], pattern: cst.MatchPattern
) -> None:
    if isinstance(pattern, cst.MatchOr):
        patterns.extend(element.pattern for element in pattern.patterns)
        return
    patterns.append(pattern)


class SequencePatternCollector:
    """Helper class to collect sequence pattern information in a single AST pass."""

    def __init__(self, subject: cst.BaseExpression):
        self.subject = subject
        self.expected_len: int | None = None
        self.min_len: int | None = None  # For >= operator (star patterns)
        self.use_star_pattern: bool = False
        self.elements: dict[int, SequenceElementPattern] = {}
        self.nested_sequences: set[int] = set()

    def collect_from_node(self, node: cst.BaseExpression) -> bool:
        """Collect pattern information from a single AST node. Returns False if invalid."""

        # Check for len(subject) == N or len(subject) >= N
        if self._is_len_check(node):
            if self.expected_len is not None or self.min_len is not None:
                return False  # Multiple len checks
            len_info = self._extract_len_value(node)
            if len_info is None:
                return False
            if isinstance(len_info, tuple):
                # (min_len, True) for >= operator
                self.min_len, self.use_star_pattern = len_info
            else:
                # Just an int for == operator
                self.expected_len = len_info
            return True

        # Check for subject[idx] == value or subject[idx] is value
        if self._is_subscript_literal_check(node):
            idx = self._extract_subscript_index(node)
            if idx is None or idx in self.elements:
                return False
            value = self._extract_comparison_value(node)
            if value is None:
                return False
            self.elements[idx] = LiteralElementPattern(value)
            return True

        or_check = self._extract_subscript_or_pattern(node)
        if or_check is not None:
            idx, pattern = or_check
            if idx in self.elements:
                return False
            self.elements[idx] = RawElementPattern(pattern)
            return True

        # Check for isinstance(subject[idx], Class)
        if self._is_subscript_isinstance_check(node):
            idx = self._extract_subscript_index(node)
            if idx is None or idx in self.elements:
                return False
            classes = self._extract_isinstance_classes(node)
            if classes is None:
                return False
            self.elements[idx] = ClassElementPattern(classes)
            # Don't mark as nested yet - will be marked later if attributes are found
            return True

        # Check for len(subject[idx]) - indicates nested sequence
        if self._is_nested_len_check(node):
            idx = self._extract_nested_index(node)
            if idx is not None:
                self.nested_sequences.add(idx)
            return True

        # Check for nested subscript patterns (subject[idx][subidx] == value)
        if self._is_nested_subscript_check(node):
            idx = self._extract_nested_index(node)
            if idx is not None and idx in self.nested_sequences:
                # This will be handled when we process nested sequences
                return True

        return True  # Skip unknown patterns

    def _is_len_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is len(subject) == N or len(subject) >= N"""
        if not m.matches(
            node,
            m.Comparison(
                comparisons=[
                    m.ComparisonTarget(operator=m.Equal() | m.GreaterThanEqual())
                ]
            ),
        ):
            return False
        comp = node  # type: ignore
        if not self._is_len_call(comp.left):
            return False
        call = comp.left  # type: ignore
        if len(call.args) == 0:
            return False
        return call.args[0].value.deep_equals(self.subject)

    def _extract_len_value(
        self, node: cst.BaseExpression
    ) -> int | tuple[int, bool] | None:
        """Extract the length constraint from len(subject) == N or len(subject) >= N.

        Returns:
            - int for == operator (exact length)
            - (int, True) for >= operator (minimum length, use star pattern)
            - None if invalid
        """
        comp = node  # type: ignore
        comparator = comp.comparisons[0].comparator
        operator = comp.comparisons[0].operator

        if m.matches(comparator, m.Integer()):
            length = int(comparator.value)  # type: ignore
            if isinstance(operator, cst.GreaterThanEqual):
                return (length, True)  # min length, use star pattern
            else:
                return length  # exact length
        return None

    def _extract_subscript_or_pattern(
        self, node: cst.BaseExpression
    ) -> tuple[int, cst.MatchPattern] | None:
        parts = flatten_boolean(node, cst.Or)
        if len(parts) <= 1:
            return None

        index: int | None = None
        patterns: list[cst.MatchPattern] = []
        for part in parts:
            part_pattern = self._extract_subscript_part_pattern(part)
            if part_pattern is None:
                return None
            part_index, pattern = part_pattern
            if index is None:
                index = part_index
            elif part_index != index:
                return None
            extend_sequence_or_patterns(patterns, pattern)

        if index is None:
            return None
        return index, build_or_pattern(patterns)

    def _extract_subscript_part_pattern(
        self, node: cst.BaseExpression
    ) -> tuple[int, cst.MatchPattern] | None:
        if self._is_subscript_literal_check(node):
            index = self._extract_subscript_index(node)
            value = self._extract_comparison_value(node)
            if index is None or value is None:
                return None
            return index, build_value_pattern(value)

        if self._is_subscript_isinstance_check(node):
            index = self._extract_subscript_index(node)
            classes = self._extract_isinstance_classes(node)
            if index is None or classes is None:
                return None
            return index, build_class_pattern(classes)

        class_pattern = self._extract_subscript_class_attribute_pattern(node)
        if class_pattern is not None:
            return class_pattern

        return None

    def _extract_subscript_class_attribute_pattern(
        self, node: cst.BaseExpression
    ) -> tuple[int, cst.MatchPattern] | None:
        if not isinstance(node, cst.BooleanOperation) or not isinstance(
            node.operator, cst.And
        ):
            return None

        components = flatten_boolean(node, cst.And)
        index: int | None = None
        classes: list[cst.BaseExpression] | None = None
        isinstance_component: cst.BaseExpression | None = None
        for component in components:
            if not self._is_subscript_isinstance_check(component):
                continue
            part_index = self._extract_subscript_index(component)
            part_classes = self._extract_isinstance_classes(component)
            if part_index is None or part_classes is None:
                return None
            if index is not None:
                return None
            index = part_index
            classes = part_classes
            isinstance_component = component

        if index is None or classes is None or isinstance_component is None:
            return None

        element_subject = cst.Subscript(
            value=self.subject,
            slice=[
                cst.SubscriptElement(slice=cst.Index(value=cst.Integer(str(index))))
            ],
        )
        if any(
            extract_attribute_path_isinstance_check(component, element_subject)
            is not None
            for component in components
        ):
            checked_paths = collect_checked_sequence_element_attribute_paths(
                components, element_subject, isinstance_component
            )
            if all(
                component is isinstance_component
                or extract_direct_attribute_check(component, element_subject)
                is not None
                or extract_attribute_path_isinstance_check(component, element_subject)
                is not None
                or extract_attribute_path_pattern_check(component, element_subject)
                is not None
                or is_redundant_attribute_path_hasattr_check(
                    component, element_subject, checked_paths
                )
                for component in components
            ):
                nested_pattern = build_sequence_element_class_pattern(
                    node, element_subject, classes
                )
                if nested_pattern is not None:
                    return index, nested_pattern

        attrs: list[tuple[str, cst.MatchPattern]] = []
        seen_attrs: set[str] = set()
        hasattr_attrs: set[str] = set()
        for component in components:
            if component is isinstance_component:
                continue
            hasattr_attr = extract_direct_hasattr_check(component, element_subject)
            if hasattr_attr is not None:
                hasattr_attrs.add(hasattr_attr)
                continue
            attr_check = extract_direct_attribute_check(component, element_subject)
            if attr_check is None:
                return None
            attr_name, pattern = attr_check
            if attr_name in seen_attrs:
                return None
            attrs.append((attr_name, pattern))
            seen_attrs.add(attr_name)

        if not attrs:
            return None
        if not hasattr_attrs <= seen_attrs:
            return None
        return index, build_class_pattern(classes, attrs)

    def _is_subscript_literal_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is subject[idx] == value or subject[idx] is value"""
        if not m.matches(
            node,
            m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())]),
        ):
            return False
        comp = node  # type: ignore
        if not m.matches(comp.left, m.Subscript()):
            return False
        subscript = comp.left  # type: ignore
        if not subscript.value.deep_equals(self.subject):
            return False
        # Validate the value is a literal/singleton
        value = comp.comparisons[0].comparator
        operator = comp.comparisons[0].operator
        if isinstance(operator, cst.Is):
            return m.matches(
                value,
                m.Name(value="None") | m.Name(value="True") | m.Name(value="False"),
            )
        else:
            return self._is_literal_value(value)

    def _extract_subscript_index(self, node: cst.BaseExpression) -> int | None:
        """Extract index from subject[idx] in a comparison or isinstance call."""
        # For comparisons: subject[idx] == value
        if m.matches(node, m.Comparison()):
            comp = node  # type: ignore
            if m.matches(comp.left, m.Subscript()):
                subscript = comp.left  # type: ignore
                return self._extract_subscript_index_from_subscript(subscript)
        # For isinstance calls: isinstance(subject[idx], Class)
        elif m.matches(node, m.Call(func=m.Name(value="isinstance"))):
            call = node  # type: ignore
            if len(call.args) >= 1 and m.matches(call.args[0].value, m.Subscript()):
                subscript = call.args[0].value  # type: ignore
                return self._extract_subscript_index_from_subscript(subscript)
        return None

    def _extract_subscript_index_from_subscript(
        self, subscript: cst.Subscript
    ) -> int | None:
        """Extract integer index from a subscript"""
        return extract_integer_subscript_index(subscript)

    def _extract_comparison_value(
        self, node: cst.BaseExpression
    ) -> cst.BaseExpression | None:
        """Extract the comparison value from subject[idx] == value"""
        comp = node  # type: ignore
        return comp.comparisons[0].comparator

    def _is_subscript_isinstance_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is isinstance(subject[idx], Class)"""
        if not m.matches(node, m.Call(func=m.Name(value="isinstance"))):
            return False
        call = node  # type: ignore
        if len(call.args) < 2:
            return False
        arg = call.args[0].value
        if not m.matches(arg, m.Subscript()):
            return False
        subscript = arg  # type: ignore
        return subscript.value.deep_equals(self.subject)

    def _extract_isinstance_classes(
        self, node: cst.BaseExpression
    ) -> list[cst.BaseExpression] | None:
        """Extract classes from isinstance(subject[idx], Class) or isinstance(subject[idx], (Class1, Class2))"""
        call = node  # type: ignore
        class_arg = call.args[1].value

        if isinstance(class_arg, cst.Tuple):
            classes = []
            for element in class_arg.elements:
                if isinstance(element, cst.Element):
                    classes.append(element.value)
                else:
                    return None  # Starred elements not supported
            return classes if classes else None
        else:
            return [class_arg]

    def _is_nested_len_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is len(subject[idx]) == N or len(subject[idx]) >= N"""
        if not m.matches(
            node,
            m.Comparison(
                comparisons=[
                    m.ComparisonTarget(operator=m.Equal() | m.GreaterThanEqual())
                ]
            ),
        ):
            return False
        comp = node  # type: ignore
        if not self._is_len_call(comp.left):
            return False
        call = comp.left  # type: ignore
        if len(call.args) == 0:
            return False
        len_arg = call.args[0].value
        if not m.matches(len_arg, m.Subscript()):
            return False
        subscript = len_arg  # type: ignore
        return subscript.value.deep_equals(self.subject)

    def _extract_nested_index(self, node: cst.BaseExpression) -> int | None:
        """Extract the index from len(subject[idx]) or subject[idx][...]"""
        comp = node  # type: ignore
        left = comp.left

        if self._is_len_call(left):
            call = left  # type: ignore
            len_arg = call.args[0].value
            subscript = len_arg  # type: ignore
        else:
            subscript = left  # type: ignore

        return self._extract_subscript_index_from_subscript(subscript)

    def _is_nested_subscript_check(self, node: cst.BaseExpression) -> bool:
        """Check if node involves subject[idx][subidx]"""
        if not m.matches(node, m.Comparison()):
            return False
        comp = node  # type: ignore
        if not m.matches(comp.left, m.Subscript()):
            return False
        subscript = comp.left  # type: ignore
        if not m.matches(subscript.value, m.Subscript()):
            return False
        inner_subscript = subscript.value  # type: ignore
        return inner_subscript.value.deep_equals(self.subject)

    def _is_literal_value(self, node: cst.BaseExpression) -> bool:
        """Check if a node is a literal value (copied from main class)"""
        # Check for unary minus/plus on numbers (e.g., -5, +3.14)
        if m.matches(node, m.UnaryOperation(operator=m.Minus() | m.Plus())):
            unary = node  # type: ignore
            return m.matches(unary.expression, m.Integer() | m.Float())

        return m.matches(
            node,
            m.Integer()
            | m.Float()
            | m.SimpleString()
            | m.ConcatenatedString()
            | m.Name(value="True")
            | m.Name(value="False")
            | m.Name(value="None"),
        )

    def _is_len_call(self, node: cst.BaseExpression) -> bool:
        """Check if node is a len() call (copied from main class)"""
        return m.matches(node, m.Call(func=m.Name(value="len"), args=[m.Arg()]))


def find_sequence_subject(test: cst.BaseExpression) -> cst.BaseExpression | None:
    subject: cst.BaseExpression | None = None
    for component in flatten_boolean(test, cst.And):
        if not isinstance(component, cst.Comparison) or len(component.comparisons) != 1:
            continue
        target = component.comparisons[0]
        if not isinstance(target.operator, (cst.Equal, cst.GreaterThanEqual)):
            continue
        if not isinstance(target.comparator, cst.Integer):
            continue
        if not m.matches(
            component.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])
        ):
            continue
        len_call = component.left  # type: ignore[assignment]
        subject = len_call.args[0].value
        break

    if subject is None or not has_direct_sequence_element_check(test, subject):
        return None
    return subject


def has_direct_sequence_element_check(
    test: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    for component in flatten_boolean(test, cst.And):
        if isinstance(component, cst.BooleanOperation) and isinstance(
            component.operator, cst.Or
        ):
            if all(
                has_direct_sequence_element_check(part, subject)
                for part in flatten_boolean(component, cst.Or)
            ):
                return True
        if isinstance(component, cst.Comparison):
            path = SubjectPath.from_expression(component.left, subject)
            if path is not None and path.starts_with_subscript:
                return True
        if isinstance(component, cst.Call) and m.matches(
            component, m.Call(func=m.Name(value="isinstance"))
        ):
            if (
                len(component.args) >= 1
                and (
                    path := SubjectPath.from_expression(
                        component.args[0].value, subject
                    )
                )
                is not None
                and path.starts_with_subscript
            ):
                return True
    return False


def build_sequence_match_list(
    pattern_infos: list[SequenceElementPattern],
    use_star: bool,
    is_top_level: bool = True,
) -> cst.MatchList:
    elements = build_sequence_elements(pattern_infos, use_star, is_top_level)
    return cst.MatchList(patterns=elements, lbracket=None, rbracket=None)


def build_bracketed_sequence_match_list(
    pattern_infos: list[SequenceElementPattern], use_star: bool
) -> cst.MatchList:
    elements = build_sequence_elements(pattern_infos, use_star, is_top_level=False)
    return cst.MatchList(
        patterns=elements,
        lbracket=cst.LeftSquareBracket(),
        rbracket=cst.RightSquareBracket(),
    )


def build_sequence_elements(
    pattern_infos: list[SequenceElementPattern], use_star: bool, is_top_level: bool
) -> list[cst.MatchSequenceElement]:
    elements = [
        cst.MatchSequenceElement(
            value=build_match_pattern_from_info(pattern_info),
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
        )
        for pattern_info in pattern_infos
    ]

    if use_star:
        elements.append(
            cst.MatchSequenceElement(value=cst.MatchStar(name=cst.Name("_")))
        )
        return elements

    if len(elements) > 1 or not is_top_level:
        last = elements[-1]
        elements[-1] = cst.MatchSequenceElement(value=last.value)
    elif elements:
        last = elements[-1]
        elements[-1] = cst.MatchSequenceElement(
            value=last.value,
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace("")),
        )
    return elements


def build_match_pattern_from_info(
    pattern_info: SequenceElementPattern,
) -> cst.MatchPattern:
    if isinstance(pattern_info, LiteralElementPattern):
        return build_value_pattern(pattern_info.value)
    if isinstance(pattern_info, ClassElementPattern):
        return build_class_pattern(pattern_info.classes)
    if isinstance(pattern_info, WildcardElementPattern):
        return cst.MatchAs(pattern=None, name=None)
    if isinstance(pattern_info, NestedSequenceElementPattern):
        return build_bracketed_sequence_match_list(
            pattern_info.elements, use_star=pattern_info.use_star
        )
    if isinstance(pattern_info, RawElementPattern):
        return pattern_info.pattern
    raise TypeError(f"Unsupported sequence element pattern: {pattern_info!r}")


def validate_wildcard_constraint(
    elements: dict[int, SequenceElementPattern], total_len: int
) -> bool:
    consecutive_wildcards = 0
    for index in range(total_len):
        if index not in elements:
            consecutive_wildcards += 1
            if consecutive_wildcards >= 3:
                return False
        else:
            consecutive_wildcards = 0
    return True


def extract_len_sequence_attribute(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> cst.Attribute | None:
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    if not isinstance(node.comparisons[0].operator, (cst.Equal, cst.GreaterThanEqual)):
        return None
    if not isinstance(node.comparisons[0].comparator, cst.Integer):
        return None
    if not m.matches(node.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
        return None
    len_call = node.left  # type: ignore[assignment]
    len_arg = len_call.args[0].value
    if isinstance(len_arg, cst.Attribute) and len_arg.value.deep_equals(subject):
        return len_arg
    return None


def is_sequence_attribute_component(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> bool:
    if isinstance(node, cst.Comparison):
        left = node.left
        if m.matches(left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
            len_call = left  # type: ignore[assignment]
            return (
                SubjectPath.from_expression(len_call.args[0].value, subject) is not None
            )
        if isinstance(left, cst.Subscript):
            return SubjectPath.from_expression(left.value, subject) is not None
        if isinstance(left, cst.Attribute):
            return SubjectPath.from_expression(left.value, subject) is not None
    if isinstance(node, cst.Call) and m.matches(
        node, m.Call(func=m.Name(value="isinstance"))
    ):
        if len(node.args) >= 1 and isinstance(node.args[0].value, cst.Subscript):
            subscript = node.args[0].value
            return SubjectPath.from_expression(subscript.value, subject) is not None
    return False


def extract_sequence_pattern_for_subject(
    condition: cst.BaseExpression, sequence_subject: cst.BaseExpression
) -> tuple[list[SequenceElementPattern], bool] | None:
    collector = SequencePatternCollector(sequence_subject)
    for component in flatten_boolean(condition, cst.And):
        if not is_component_for_sequence_subject(component, sequence_subject):
            continue
        if not collector.collect_from_node(component):
            return None

    for index in collector.nested_sequences:
        nested_result = extract_nested_sequence_element(
            condition, sequence_subject, index
        )
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

    if not collector.elements and collector.min_len is None:
        return None
    if not use_star:
        if max(collector.elements) >= required_len:
            return None
        if not validate_wildcard_constraint(collector.elements, required_len):
            return None

    pattern_infos = []
    for index in range(required_len):
        pattern_info = collector.elements.get(index, WildcardElementPattern())
        if isinstance(pattern_info, ClassElementPattern):
            element_subject = cst.Subscript(
                value=sequence_subject,
                slice=[
                    cst.SubscriptElement(slice=cst.Index(value=cst.Integer(str(index))))
                ],
            )
            nested_pattern = build_sequence_element_class_pattern(
                condition, element_subject, pattern_info.classes
            )
            if nested_pattern is not None:
                pattern_info = RawElementPattern(nested_pattern)
        pattern_infos.append(pattern_info)

    return (pattern_infos, use_star)


def is_component_for_sequence_subject(
    component: cst.BaseExpression, sequence_subject: cst.BaseExpression
) -> bool:
    if isinstance(component, cst.BooleanOperation) and isinstance(
        component.operator, cst.Or
    ):
        return all(
            is_component_for_sequence_subject(part, sequence_subject)
            for part in flatten_boolean(component, cst.Or)
        )

    if isinstance(component, cst.Comparison):
        if m.matches(component.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
            len_call = component.left  # type: ignore[assignment]
            len_arg = len_call.args[0].value
            path = SubjectPath.from_expression(len_arg, sequence_subject)
            return path is not None and (path.is_subject or path.starts_with_subscript)
        if isinstance(component.left, cst.Subscript):
            path = SubjectPath.from_expression(component.left, sequence_subject)
            return path is not None and path.starts_with_subscript
        if isinstance(component.left, cst.Attribute):
            path = SubjectPath.from_expression(component.left.value, sequence_subject)
            return path is not None and (path.is_subject or path.starts_with_subscript)
    if isinstance(component, cst.Call) and m.matches(
        component, m.Call(func=m.Name(value="isinstance"))
    ):
        if len(component.args) >= 1:
            path = SubjectPath.from_expression(
                component.args[0].value, sequence_subject
            )
            return path is not None and path.starts_with_subscript
    return False


def build_sequence_element_class_pattern(
    condition: cst.BaseExpression,
    element_subject: cst.BaseExpression,
    class_exprs: list[cst.BaseExpression],
) -> cst.MatchPattern | None:
    sequence_subjects: dict[str, cst.Attribute] = {}
    scalar_attrs: list[tuple[str, cst.MatchPattern]] = []
    nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]] = {}
    nested_scalar_checks: dict[tuple[str, ...], cst.MatchPattern] = {}
    nested_sequence_checks: dict[tuple[str, ...], cst.BaseExpression] = {}
    for component in flatten_boolean(condition, cst.And):
        sequence_subject = extract_len_sequence_attribute(component, element_subject)
        if sequence_subject is not None:
            sequence_subjects[sequence_subject.attr.value] = sequence_subject
            continue

        nested_sequence_check = extract_attribute_path_sequence_len_check(
            component, element_subject
        )
        if nested_sequence_check is not None:
            path, sequence_subject = nested_sequence_check
            nested_sequence_checks[path] = sequence_subject
            continue

        nested_isinstance = extract_attribute_path_isinstance_check(
            component, element_subject
        )
        if nested_isinstance is not None:
            path, classes = nested_isinstance
            nested_classes[path] = classes
            continue

        nested_scalar_check = extract_attribute_path_pattern_check(
            component, element_subject
        )
        if nested_scalar_check is not None:
            path, pattern = nested_scalar_check
            nested_scalar_checks[path] = pattern
            continue

        attr_check = extract_direct_attribute_check(component, element_subject)
        if attr_check is not None:
            attr_name, value = attr_check
            scalar_attrs.append((attr_name, value))

    if (
        not sequence_subjects
        and not scalar_attrs
        and not nested_classes
        and not nested_scalar_checks
        and not nested_sequence_checks
    ):
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
    for attr_name, pattern in scalar_attrs:
        if attr_name in sequence_subjects:
            continue
        keyword_patterns.append((attr_name, pattern))
        used_attrs.add(attr_name)

    if nested_classes or nested_scalar_checks or nested_sequence_checks:
        nested_patterns = build_nested_sequence_element_keyword_patterns(
            condition,
            nested_classes,
            nested_scalar_checks,
            nested_sequence_checks,
        )
        if nested_patterns is None:
            return None
        for attr_name, pattern in nested_patterns:
            if attr_name in used_attrs:
                continue
            keyword_patterns.append((attr_name, pattern))
            used_attrs.add(attr_name)

    return build_class_pattern(class_exprs, keyword_patterns)


def build_nested_sequence_element_keyword_patterns(
    condition: cst.BaseExpression,
    nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]],
    scalar_checks: dict[tuple[str, ...], cst.MatchPattern],
    sequence_checks: dict[tuple[str, ...], cst.BaseExpression],
) -> list[tuple[str, cst.MatchPattern]] | None:
    names = {
        path[0]
        for path in set(nested_classes) | set(scalar_checks) | set(sequence_checks)
        if path
    }
    keyword_patterns: list[tuple[str, cst.MatchPattern]] = []
    for name in sorted(names):
        path = (name,)
        pattern = build_nested_sequence_element_pattern(
            condition, path, nested_classes, scalar_checks, sequence_checks
        )
        if pattern is None:
            return None
        keyword_patterns.append((name, pattern))
    return keyword_patterns


def build_nested_sequence_element_pattern(
    condition: cst.BaseExpression,
    path: tuple[str, ...],
    nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]],
    scalar_checks: dict[tuple[str, ...], cst.MatchPattern],
    sequence_checks: dict[tuple[str, ...], cst.BaseExpression],
) -> cst.MatchPattern | None:
    if path in sequence_checks:
        sequence_result = extract_sequence_pattern_for_subject(
            condition, sequence_checks[path]
        )
        if sequence_result is None:
            return None
        pattern_infos, use_star = sequence_result
        return build_bracketed_sequence_match_list(pattern_infos, use_star)

    if path in nested_classes:
        class_patterns = []
        for class_expr in nested_classes[path]:
            class_pattern = build_nested_sequence_element_class_pattern(
                condition,
                class_expr,
                path,
                nested_classes,
                scalar_checks,
                sequence_checks,
            )
            if class_pattern is None:
                return None
            class_patterns.append(class_pattern)
        return build_or_pattern(class_patterns)

    return scalar_checks.get(path)


def build_nested_sequence_element_class_pattern(
    condition: cst.BaseExpression,
    class_expr: cst.BaseExpression,
    path: tuple[str, ...],
    nested_classes: dict[tuple[str, ...], list[cst.BaseExpression]],
    scalar_checks: dict[tuple[str, ...], cst.MatchPattern],
    sequence_checks: dict[tuple[str, ...], cst.BaseExpression],
) -> cst.MatchClass | None:
    child_names = {
        child_path[len(path)]
        for child_path in set(nested_classes)
        | set(scalar_checks)
        | set(sequence_checks)
        if len(child_path) > len(path) and child_path[: len(path)] == path
    }
    kwds: list[cst.MatchKeywordElement] = []
    for name in sorted(child_names):
        child_path = path + (name,)
        child_pattern = build_nested_sequence_element_pattern(
            condition,
            child_path,
            nested_classes,
            scalar_checks,
            sequence_checks,
        )
        if child_pattern is None:
            return None
        kwds.append(cst.MatchKeywordElement(key=cst.Name(name), pattern=child_pattern))
    return cst.MatchClass(cls=class_expr, patterns=[], kwds=kwds)


def extract_direct_attribute_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[str, cst.MatchPattern] | None:
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    if not isinstance(node.left, cst.Attribute):
        return None
    if not node.left.value.deep_equals(subject):
        return None

    target = node.comparisons[0]
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return None
    if isinstance(target.operator, cst.Is) and not m.matches(
        target.comparator,
        m.Name(value="None") | m.Name(value="True") | m.Name(value="False"),
    ):
        return None
    if not SequencePatternCollector(subject)._is_literal_value(target.comparator):
        return None

    return node.left.attr.value, build_value_pattern(target.comparator)


def extract_direct_hasattr_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> str | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"))
    ):
        return None
    if len(node.args) != 2:
        return None
    if not node.args[0].value.deep_equals(subject):
        return None

    name_arg = node.args[1].value
    if not isinstance(name_arg, cst.SimpleString):
        return None
    try:
        value = cst.ensure_type(cst.parse_expression(name_arg.value), cst.SimpleString)
    except cst.ParserSyntaxError:
        return None
    literal = value.evaluated_value
    return literal if isinstance(literal, str) else None


def collect_checked_sequence_element_attribute_paths(
    components: list[cst.BaseExpression],
    subject: cst.BaseExpression,
    isinstance_component: cst.BaseExpression,
) -> set[tuple[str, ...]]:
    checked_paths: set[tuple[str, ...]] = set()
    for component in components:
        if component is isinstance_component:
            continue
        attr_check = extract_direct_attribute_check(component, subject)
        if attr_check is not None:
            attr_name, _pattern = attr_check
            checked_paths.add((attr_name,))
            continue

        nested_isinstance = extract_attribute_path_isinstance_check(component, subject)
        if nested_isinstance is not None:
            path, _classes = nested_isinstance
            checked_paths.add(path)
            continue

        nested_pattern = extract_attribute_path_pattern_check(component, subject)
        if nested_pattern is not None:
            path, _pattern = nested_pattern
            checked_paths.add(path)
            continue

        nested_sequence = extract_attribute_path_sequence_len_check(component, subject)
        if nested_sequence is not None:
            path, _sequence_subject = nested_sequence
            checked_paths.add(path)
            continue

    return checked_paths


def is_redundant_attribute_path_hasattr_check(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[tuple[str, ...]],
) -> bool:
    hasattr_path = extract_attribute_path_hasattr_check(node, subject)
    if hasattr_path is None:
        return False
    return any(
        path == hasattr_path or path[: len(hasattr_path)] == hasattr_path
        for path in checked_paths
    )


def extract_attribute_path_hasattr_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> tuple[str, ...] | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"))
    ):
        return None
    if len(node.args) != 2:
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:
        return None

    attr_names: list[str] = []
    for part in path.parts:
        if not isinstance(part, AttributePathPart):
            return None
        attr_names.append(part.name)

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
    return (*attr_names, literal)


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


def extract_attribute_path_isinstance_check(
    node: cst.BaseExpression, subject: cst.BaseExpression
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

    class_exprs = extract_isinstance_classes(node.args[1].value, r".*_TYPES$")
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


def extract_sequence_element_direct_attribute_check(
    node: cst.BaseExpression, sequence_subject: cst.BaseExpression
) -> tuple[int, str, cst.BaseExpression] | None:
    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return None
    if not isinstance(node.left, cst.Attribute):
        return None

    target = node.comparisons[0]
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return None
    if isinstance(target.operator, cst.Is) and not m.matches(
        target.comparator,
        m.Name(value="None") | m.Name(value="True") | m.Name(value="False"),
    ):
        return None
    if not SequencePatternCollector(sequence_subject)._is_literal_value(
        target.comparator
    ):
        return None

    element_path = SubjectPath.from_expression(node.left.value, sequence_subject)
    if (
        element_path is None
        or len(element_path.parts) != 1
        or not isinstance(element_path.parts[0], SubscriptPathPart)
        or element_path.parts[0].index is None
    ):
        return None

    return element_path.parts[0].index, node.left.attr.value, target.comparator


def extract_nested_sequence_element(
    condition: cst.BaseExpression, subject: cst.BaseExpression, index: int
) -> tuple[list[SequenceElementPattern], bool] | None:
    nested_subject = cst.Subscript(
        value=subject,
        slice=[cst.SubscriptElement(slice=cst.Index(value=cst.Integer(str(index))))],
    )
    nested_result = extract_sequence_pattern_for_subject(condition, nested_subject)
    if nested_result is None:
        return None
    return nested_result
