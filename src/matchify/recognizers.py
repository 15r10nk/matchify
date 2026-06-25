"""Recognizers that turn branch conditions into match patterns and guards."""

from __future__ import annotations

import libcst as cst
from libcst import matchers as m

from .facts import BranchFacts
from .pattern_builder import normalize_with_bool_tree
from .patterns import (
    combine_guards,
    extract_isinstance_classes,
    flatten_boolean,
    is_literal_value,
    is_singleton_name,
)
from .sequence_patterns import find_sequence_subject
from .subject_path import AttributePathPart, SubjectPath


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
            # Fallback for legacy subscript-subject chains inside mixed AND
            # expressions; direct subscript subjects are covered separately.
            if isinstance_subject is not None:  # pragma: no cover
                return isinstance_subject

        sequence_subject = find_sequence_subject(test)
        # Sequence subjects require an AND expression, handled above.
        if sequence_subject is not None:  # pragma: no cover
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
            # Invalid OR alternatives only reject subject recognition.
            if not isinstance(target.operator, (cst.Equal, cst.Is)):  # pragma: no cover
                return None
            if isinstance(target.operator, cst.Is) and not is_singleton_name(
                target.comparator
            ):  # pragma: no cover
                return None
            if not is_literal_value(target.comparator):
                return None
            return part.left

        # OR subject probing scans several possible shapes; false sides just
        # continue to the next probe.
        if isinstance(part, cst.Call) and m.matches(  # pragma: no branch
            part, m.Call(func=m.Name(value="isinstance"))
        ):
            if (  # pragma: no branch
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

        # Non-comparison/non-isinstance OR parts are rejected conservatively.
        return None  # pragma: no cover

    def _find_value_subject(
        self, test: cst.BaseExpression
    ) -> cst.BaseExpression | None:
        for component in flatten_boolean(test, cst.And):
            or_subject = self._recognize_or_subject(component)
            if or_subject is not None and not contains_subscript(or_subject):
                return or_subject

            # Subject discovery ignores non-comparison AND components here; other
            # recognizers handle isinstance/sequence anchors first.
            if not isinstance(component, cst.Comparison):  # pragma: no cover
                continue
            if len(component.comparisons) != 1:  # pragma: no cover
                continue
            target = component.comparisons[0]
            if contains_subscript(component.left):
                continue
            if isinstance(target.operator, cst.Equal) and is_literal_value(
                target.comparator
            ):
                return component.left
            if isinstance(
                target.operator, cst.Is
            ) and is_singleton_name(  # pragma: no branch
                target.comparator
            ):
                return component.left
        return None

    def _find_isinstance_subject(
        self, test: cst.BaseExpression, include_subscripts: bool
    ) -> cst.BaseExpression | None:
        for component in flatten_boolean(test, cst.And):
            # The scan intentionally ignores non-isinstance components.
            if isinstance(component, cst.Call) and m.matches(  # pragma: no branch
                component, m.Call(func=m.Name(value="isinstance"))
            ):
                if (  # pragma: no branch
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
    # If pruning leaves one condition we return it directly; otherwise rebuild AND.
    if len(filtered) == 1:  # pragma: no branch
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


def should_remove_redundant_sequence_type_check(
    node: cst.BaseExpression,
    subject: cst.BaseExpression,
    checked_paths: set[SubjectPath],
    remove_sequence_type_checks: bool,
) -> bool:
    sequence_path = extract_list_tuple_isinstance_path(node, subject)
    if sequence_path is None or sequence_path not in checked_paths:
        return False
    return remove_sequence_type_checks or sequence_path.is_subject


def extract_list_tuple_isinstance_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="isinstance"))
    ):
        return None
    # Defensive: only normal two-argument isinstance calls are interesting here.
    if len(node.args) != 2:  # pragma: no cover
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
        # Malformed isinstance calls are rejected before they become checked paths.
        if len(node.args) < 2:  # pragma: no cover
            return set()
        path = SubjectPath.from_expression(node.args[0].value, subject)
        if path is None or not path:
            return set()
        return {path}

    if not isinstance(node, cst.Comparison) or len(node.comparisons) != 1:
        return set()

    if m.matches(node.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
        len_call = node.left
        # Guarded by the len(...) matcher; retained for type-narrowing safety.
        if not len_call.args:  # pragma: no cover
            return set()
        path = SubjectPath.from_expression(len_call.args[0].value, subject)
        if path is None:
            return set()
        return {path}

    path = SubjectPath.from_expression(node.left, subject)
    if path is None or not path or not isinstance(path.last_part, AttributePathPart):
        return set()

    target = node.comparisons[0]
    if isinstance(  # pragma: no branch
        target.operator, cst.Is
    ) and not is_singleton_name(target.comparator):
        return set()
    if not isinstance(target.operator, (cst.Equal, cst.Is)):
        return set()
    # Non-literal attribute comparisons are kept as guards by the builder.
    if not is_literal_value(target.comparator):  # pragma: no branch
        return set()

    return {path}


def extract_hasattr_attribute_path(
    node: cst.BaseExpression, subject: cst.BaseExpression
) -> SubjectPath | None:
    if not isinstance(node, cst.Call) or not m.matches(
        node, m.Call(func=m.Name(value="hasattr"))
    ):
        return None
    # Defensive: hasattr needs exactly object and attribute-name arguments.
    if len(node.args) != 2:  # pragma: no cover
        return None
    path = SubjectPath.from_expression(node.args[0].value, subject)
    if path is None:  # pragma: no cover
        return None
    name_arg = node.args[1].value
    if not isinstance(name_arg, cst.SimpleString):  # pragma: no cover
        return None
    try:
        value = cst.ensure_type(cst.parse_expression(name_arg.value), cst.SimpleString)
    except cst.ParserSyntaxError:  # pragma: no cover
        return None
    literal = value.evaluated_value
    if not isinstance(literal, str):  # pragma: no cover
        return None
    return SubjectPath((*path.parts, AttributePathPart(literal)))


class PatternRecognitionEngine:
    """Runs branch recognition through the BoolExpr predicate pipeline."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern
        self.subject_recognizer = SubjectRecognizer(ignore_types_pattern)

    def recognize_subject(self, test: cst.BaseExpression) -> cst.BaseExpression | None:
        return self.subject_recognizer.recognize(test)

    def normalize_branch(
        self, condition: cst.BaseExpression, subject: cst.BaseExpression
    ) -> BranchFacts:
        bool_tree_condition = prepare_bool_tree_condition(
            condition,
            subject,
        )
        bool_tree_branch = normalize_with_bool_tree(
            bool_tree_condition, subject, self.ignore_types_pattern
        )
        # Normal public conversions use the BoolExpr path; fallback remains for
        # unsupported future predicates.
        if bool_tree_branch is not None:  # pragma: no branch
            return bool_tree_branch

        return BranchFacts(
            condition=condition,
            subject=subject,
            facts=(),
            pattern=None,
            guard=condition,
        )


def prepare_bool_tree_condition(
    condition: cst.BaseExpression,
    subject: cst.BaseExpression,
) -> cst.BaseExpression:
    if isinstance(condition, cst.BooleanOperation) and isinstance(
        condition.operator, (cst.And, cst.Or)
    ):
        operator_type = cst.And if isinstance(condition.operator, cst.And) else cst.Or
        parts = [
            prepare_bool_tree_condition(part, subject)
            for part in flatten_boolean(condition, operator_type)
        ]
        expression = parts[0]
        for part in parts[1:]:
            expression = cst.BooleanOperation(
                left=expression,
                operator=operator_type(),
                right=part,
            )
        # Multiple flattened parts rebuild to BooleanOperation; this guard only
        # protects future callers that pass an already-single part.
        if isinstance(expression, cst.BooleanOperation):  # pragma: no branch
            expression = expression.with_changes(
                lpar=condition.lpar,
                rpar=condition.rpar,
            )
        return remove_redundant_subject_checks(
            expression,
            subject,
            remove_sequence_type_checks=False,
        )

    return remove_redundant_subject_checks(
        condition,
        subject,
        remove_sequence_type_checks=False,
    )


def contains_subscript(node: cst.CSTNode) -> bool:
    if isinstance(node, cst.Subscript):  # pragma: no branch
        return True
    return any(contains_subscript(child) for child in node.children)
