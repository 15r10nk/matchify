import random
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from itertools import product
from pathlib import Path

from matchify.cli import convert_file

MAX_SAMPLE_VALUES_PER_CASE = 24


@dataclass(frozen=True)
class LiteralPattern:
    """Generates `subject == value`, which corresponds to `case value:`."""

    value: str

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return f"{subject} == {self.value}"

    def to_value_code(self) -> str:
        return self.value


@dataclass(frozen=True)
class SingletonPattern:
    """Generates `subject is None/True/False`, matching `case None/True/False:`."""

    value: str

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return f"{subject} is {self.value}"

    def to_value_code(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrPattern:
    """Generates OR conditions, matching `case a | Class() | ...:`."""

    alternatives: tuple["GeneratedPattern", ...]

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        condition = " or ".join(
            pattern.to_condition_code(subject, safe=safe)
            for pattern in self.alternatives
        )
        return f"({condition})"

    def to_value_code(self) -> str:
        return self.alternatives[0].to_value_code()


@dataclass(frozen=True)
class ClassPattern:
    """Generates `isinstance(subject, C) and ...`, matching `case C(...):`."""

    class_name: str
    attrs: tuple[tuple[str, "GeneratedPattern"], ...] = ()

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = [f"isinstance({subject}, {self.class_name})"]
        for attr, pattern in sorted(self.attrs, key=class_attr_sort_key):
            if safe:
                parts.append(f"hasattr({subject}, {attr!r})")
            parts.append(pattern.to_condition_code(f"{subject}.{attr}", safe=safe))
        return " and ".join(parts)

    def to_value_code(self) -> str:
        if not self.attrs:
            return f"{self.class_name}()"
        attrs = ", ".join(
            f"{attr}={pattern.to_value_code()}"
            for attr, pattern in sorted(self.attrs, key=class_attr_sort_key)
        )
        return f"{self.class_name}({attrs})"


@dataclass(frozen=True)
class ClassUnionPattern:
    """Generates `isinstance(subject, (A, B))`, matching `case A(...) | B(...):`."""

    class_names: tuple[str, ...]
    attrs: tuple[tuple[str, "GeneratedPattern"], ...] = ()

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        classes = ", ".join(self.class_names)
        parts = [f"isinstance({subject}, ({classes}))"]
        for attr, pattern in sorted(self.attrs, key=class_attr_sort_key):
            if safe:
                parts.append(f"hasattr({subject}, {attr!r})")
            parts.append(pattern.to_condition_code(f"{subject}.{attr}", safe=safe))
        return " and ".join(parts)

    def to_value_code(self) -> str:
        return ClassPattern(self.class_names[0], self.attrs).to_value_code()


@dataclass(frozen=True)
class GuardedPattern:
    """Adds `and GUARD` to a base pattern, matching `case pattern if GUARD:`."""

    pattern: "GeneratedPattern"
    guard: str

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        guard = self.guard.format(subject=subject)
        return f"{self.pattern.to_condition_code(subject, safe=safe)} and {guard}"

    def to_value_code(self) -> str:
        return self.pattern.to_value_code()


@dataclass(frozen=True)
class AttributeGuardedClassPattern:
    """Generates `isinstance(subject, C) and subject.attr == expr` as a guard."""

    class_name: str
    attr: str
    guard_expr: str
    value: str

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = [f"isinstance({subject}, {self.class_name})"]
        if safe:
            parts.append(f"hasattr({subject}, {self.attr!r})")
        parts.append(f"{subject}.{self.attr} == {self.guard_expr}")
        return " and ".join(parts)

    def to_value_code(self) -> str:
        return f"{self.class_name}({self.attr}={self.value})"


@dataclass(frozen=True)
class RelationalGuardedClassPattern:
    """Generates `isinstance(subject, C) and subject.attr > n` as a guard."""

    class_name: str
    attr: str
    operator: str
    threshold: str
    value: str
    fallthrough_value: str

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = [f"isinstance({subject}, {self.class_name})"]
        if safe:
            parts.append(f"hasattr({subject}, {self.attr!r})")
        parts.append(f"{subject}.{self.attr} {self.operator} {self.threshold}")
        return " and ".join(parts)

    def to_value_code(self) -> str:
        return f"{self.class_name}({self.attr}={self.value})"


@dataclass(frozen=True)
class CaptureClassPattern:
    """Generates `len(subject.attr) >= n` plus body captures from that attribute."""

    class_name: str
    attr: str
    capture_indices: tuple[int, ...]

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = [f"isinstance({subject}, {self.class_name})"]
        if safe:
            parts.extend(
                [
                    f"hasattr({subject}, {self.attr!r})",
                    f"isinstance({subject}.{self.attr}, (list, tuple))",
                ]
            )
        parts.append(f"len({subject}.{self.attr}) >= {self.required_length()}")
        return " and ".join(parts)

    def to_value_code(self) -> str:
        elements = ", ".join(str(index + 1) for index in range(self.required_length()))
        return f"{self.class_name}({self.attr}=[{elements}, object()])"

    def capture_assignments(
        self, subject: str, case_index: int, names: list[str]
    ) -> list[str]:
        lines = []
        start = len(names)
        for capture_number, capture_index in enumerate(self.capture_indices):
            name = f"capture_{case_index}_{start + capture_number}"
            names.append(name)
            lines.append(f"{name} = {subject}.{self.attr}[{capture_index}]")
        return lines

    def required_length(self) -> int:
        return max(self.capture_indices) + 1


@dataclass(frozen=True)
class SequenceCapturePattern:
    """Generates sequence checks plus body captures from the sequence subject."""

    checked_index: int
    checked_pattern: "GeneratedPattern"
    capture_indices: tuple[int, ...]
    tuple_value: bool = False

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = []
        if safe:
            parts.append(f"isinstance({subject}, (list, tuple))")
        parts.append(f"len({subject}) >= {self.required_length()}")
        parts.append(
            self.checked_pattern.to_condition_code(
                f"{subject}[{self.checked_index}]", safe=safe
            )
        )
        return " and ".join(parts)

    def to_value_code(self) -> str:
        elements = ["object()"] * self.required_length()
        elements[self.checked_index] = self.checked_pattern.to_value_code()
        for capture_index in self.capture_indices:
            if capture_index != self.checked_index:
                elements[capture_index] = str(capture_index + 1)
        return sequence_value_code(
            ", ".join(elements),
            tuple_value=self.tuple_value,
            element_count=len(elements),
        )

    def capture_assignments(
        self, subject: str, case_index: int, names: list[str]
    ) -> list[str]:
        lines = []
        start = len(names)
        for capture_number, capture_index in enumerate(self.capture_indices):
            name = f"capture_{case_index}_{start + capture_number}"
            names.append(name)
            lines.append(f"{name} = {subject}[{capture_index}]")
        return lines

    def required_length(self) -> int:
        return max(self.checked_index, *self.capture_indices) + 1


@dataclass(frozen=True)
class SequencePattern:
    """Generates `len(subject) == n and subject[i] ...`, matching sequence cases."""

    elements: tuple["GeneratedPattern", ...]
    bracketed: bool
    tuple_value: bool = False

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = []
        if safe:
            parts.append(f"isinstance({subject}, (list, tuple))")
        parts.append(f"len({subject}) == {len(self.elements)}")
        for index, element in enumerate(self.elements):
            parts.append(element.to_condition_code(f"{subject}[{index}]", safe=safe))
        return " and ".join(parts)

    def to_value_code(self) -> str:
        elements = ", ".join(element.to_value_code() for element in self.elements)
        return sequence_value_code(
            elements, tuple_value=self.tuple_value, element_count=len(self.elements)
        )


@dataclass(frozen=True)
class GappedSequencePattern:
    """Generates `len(subject) == n` with skipped indices, matching `_` gaps."""

    elements: tuple["GeneratedPattern | None", ...]
    bracketed: bool
    tuple_value: bool = False

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = []
        if safe:
            parts.append(f"isinstance({subject}, (list, tuple))")
        parts.append(f"len({subject}) == {len(self.elements)}")
        for index, element in enumerate(self.elements):
            if element is not None:
                parts.append(
                    element.to_condition_code(f"{subject}[{index}]", safe=safe)
                )
        return " and ".join(parts)

    def to_value_code(self) -> str:
        elements = ", ".join(
            element.to_value_code() if element is not None else "object()"
            for element in self.elements
        )
        return sequence_value_code(
            elements, tuple_value=self.tuple_value, element_count=len(self.elements)
        )


@dataclass(frozen=True)
class StarSequencePattern:
    """Generates `len(subject) >= n and subject[i] ...`, matching `case [..., *_]:`."""

    elements: tuple["GeneratedPattern", ...]
    tuple_value: bool = False

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = []
        if safe:
            parts.append(f"isinstance({subject}, (list, tuple))")
        parts.append(f"len({subject}) >= {len(self.elements)}")
        for index, element in enumerate(self.elements):
            parts.append(element.to_condition_code(f"{subject}[{index}]", safe=safe))
        return " and ".join(parts)

    def to_value_code(self) -> str:
        elements = ", ".join(
            [*(element.to_value_code() for element in self.elements), "object()"]
        )
        return sequence_value_code(
            elements,
            tuple_value=self.tuple_value,
            element_count=len(self.elements) + 1,
        )


@dataclass(frozen=True)
class GappedStarSequencePattern:
    """Generates `len(subject) >= n` with skipped prefix indices before `*_`."""

    elements: tuple["GeneratedPattern | None", ...]
    tuple_value: bool = False

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        parts = []
        if safe:
            parts.append(f"isinstance({subject}, (list, tuple))")
        parts.append(f"len({subject}) >= {len(self.elements)}")
        for index, element in enumerate(self.elements):
            if element is not None:
                parts.append(
                    element.to_condition_code(f"{subject}[{index}]", safe=safe)
                )
        return " and ".join(parts)

    def to_value_code(self) -> str:
        elements = ", ".join(
            [
                *(
                    element.to_value_code() if element is not None else "object()"
                    for element in self.elements
                ),
                "object()",
            ]
        )
        return sequence_value_code(
            elements,
            tuple_value=self.tuple_value,
            element_count=len(self.elements) + 1,
        )


@dataclass(frozen=True)
class WildcardPattern:
    """Generates the final `else` branch, matching wildcard `case _:`."""

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return "True"

    def to_value_code(self) -> str:
        return "object()"


GeneratedPattern = (
    LiteralPattern
    | SingletonPattern
    | OrPattern
    | ClassPattern
    | ClassUnionPattern
    | GuardedPattern
    | AttributeGuardedClassPattern
    | RelationalGuardedClassPattern
    | CaptureClassPattern
    | SequenceCapturePattern
    | SequencePattern
    | GappedSequencePattern
    | StarSequencePattern
    | GappedStarSequencePattern
    | WildcardPattern
)


def class_attr_sort_key(attr_pattern: tuple[str, GeneratedPattern]) -> tuple[int, str]:
    attr, pattern = attr_pattern
    if isinstance(pattern, GuardedPattern):
        return class_attr_sort_key((attr, pattern.pattern))
    is_sequence = isinstance(
        pattern,
        (
            SequencePattern,
            GappedSequencePattern,
            StarSequencePattern,
            GappedStarSequencePattern,
        ),
    )
    return (0 if is_sequence else 1, attr)


def collect_capture_assignments(
    pattern: GeneratedPattern, subject: str, case_index: int, names: list[str]
) -> list[str]:
    if isinstance(pattern, CaptureClassPattern):
        return pattern.capture_assignments(subject, case_index, names)
    if isinstance(pattern, SequenceCapturePattern):
        return pattern.capture_assignments(subject, case_index, names)
    if isinstance(pattern, OrPattern):
        signatures = [
            capture_signature(alternative) for alternative in pattern.alternatives
        ]
        if (
            not signatures
            or signatures[0] == ()
            or any(signature != signatures[0] for signature in signatures[1:])
        ):
            return []
        return collect_capture_assignments(
            pattern.alternatives[0], subject, case_index, names
        )
    if isinstance(pattern, GuardedPattern):
        return collect_capture_assignments(pattern.pattern, subject, case_index, names)
    if isinstance(pattern, (ClassPattern, ClassUnionPattern)):
        lines = []
        for attr, attr_pattern in sorted(pattern.attrs, key=class_attr_sort_key):
            lines.extend(
                collect_capture_assignments(
                    attr_pattern, f"{subject}.{attr}", case_index, names
                )
            )
        return lines
    if isinstance(pattern, SequencePattern):
        lines = []
        for index, element in enumerate(pattern.elements):
            lines.extend(
                collect_capture_assignments(
                    element, f"{subject}[{index}]", case_index, names
                )
            )
        return lines
    if isinstance(pattern, GappedSequencePattern):
        lines = []
        for index, element in enumerate(pattern.elements):
            if element is not None:
                lines.extend(
                    collect_capture_assignments(
                        element, f"{subject}[{index}]", case_index, names
                    )
                )
        return lines
    if isinstance(pattern, StarSequencePattern):
        lines = []
        for index, element in enumerate(pattern.elements):
            lines.extend(
                collect_capture_assignments(
                    element, f"{subject}[{index}]", case_index, names
                )
            )
        return lines
    if isinstance(pattern, GappedStarSequencePattern):
        lines = []
        for index, element in enumerate(pattern.elements):
            if element is not None:
                lines.extend(
                    collect_capture_assignments(
                        element, f"{subject}[{index}]", case_index, names
                    )
                )
        return lines
    return []


CaptureSignature = tuple[tuple[tuple[str, ...], tuple[int, ...]], ...]


def capture_signature(pattern: GeneratedPattern) -> CaptureSignature:
    if isinstance(pattern, CaptureClassPattern):
        return (((pattern.attr,), pattern.capture_indices),)
    if isinstance(pattern, SequenceCapturePattern):
        return (((), pattern.capture_indices),)
    if isinstance(pattern, GuardedPattern):
        return capture_signature(pattern.pattern)
    if isinstance(pattern, (ClassPattern, ClassUnionPattern)):
        signatures = []
        for attr, attr_pattern in sorted(pattern.attrs, key=class_attr_sort_key):
            signatures.extend(
                ((attr, *path), indices)
                for path, indices in capture_signature(attr_pattern)
            )
        return tuple(signatures)
    if isinstance(pattern, SequencePattern):
        return tuple(
            ((f"[{index}]", *path), indices)
            for index, element in enumerate(pattern.elements)
            for path, indices in capture_signature(element)
        )
    if isinstance(pattern, GappedSequencePattern):
        return tuple(
            ((f"[{index}]", *path), indices)
            for index, element in enumerate(pattern.elements)
            if element is not None
            for path, indices in capture_signature(element)
        )
    if isinstance(pattern, StarSequencePattern):
        return tuple(
            ((f"[{index}]", *path), indices)
            for index, element in enumerate(pattern.elements)
            for path, indices in capture_signature(element)
        )
    if isinstance(pattern, GappedStarSequencePattern):
        return tuple(
            ((f"[{index}]", *path), indices)
            for index, element in enumerate(pattern.elements)
            if element is not None
            for path, indices in capture_signature(element)
        )
    return ()


def contains_capture(pattern: GeneratedPattern) -> bool:
    if isinstance(pattern, (CaptureClassPattern, SequenceCapturePattern)):
        return True
    if isinstance(pattern, OrPattern):
        return any(
            contains_capture(alternative) for alternative in pattern.alternatives
        )
    if isinstance(pattern, GuardedPattern):
        return contains_capture(pattern.pattern)
    if isinstance(pattern, (ClassPattern, ClassUnionPattern)):
        return any(contains_capture(attr_pattern) for _, attr_pattern in pattern.attrs)
    if isinstance(pattern, SequencePattern):
        return any(contains_capture(element) for element in pattern.elements)
    if isinstance(pattern, GappedSequencePattern):
        return any(
            element is not None and contains_capture(element)
            for element in pattern.elements
        )
    if isinstance(pattern, StarSequencePattern):
        return any(contains_capture(element) for element in pattern.elements)
    if isinstance(pattern, GappedStarSequencePattern):
        return any(
            element is not None and contains_capture(element)
            for element in pattern.elements
        )
    return False


@dataclass(frozen=True)
class GeneratedCase:
    pattern: GeneratedPattern
    body: str

    def trace_body_code(self, subject: str, case_index: int) -> str:
        names: list[str] = []
        assignments = collect_capture_assignments(
            self.pattern, subject, case_index, names
        )
        if assignments:
            return "\n".join([*assignments, f"print({self.body!r})"])
        return f"print({self.body!r})"


@dataclass(frozen=True)
class GeneratedProgram:
    classes: tuple[str, ...]
    cases: tuple[GeneratedCase, ...]

    def class_defs_code(self) -> str:
        return "\n".join(
            f"class {class_name}:\n"
            "    def __init__(self, **attrs):\n"
            "        self.__dict__.update(attrs)\n"
            for class_name in self.classes
        )

    def to_if_code(self, value_code: str = "None", safe: bool = False) -> str:
        class_defs = self.class_defs_code()
        branch_blocks = []
        for index, case in enumerate(self.cases):
            if isinstance(case.pattern, WildcardPattern):
                branch_blocks.append(f"else:\n    result = {case.body!r}")
                continue
            keyword = "if" if index == 0 else "elif"
            condition = case.pattern.to_condition_code("value", safe=safe)
            branch_blocks.append(f"{keyword} {condition}:\n    result = {case.body!r}")
        branches = "\n".join(branch_blocks)
        return f"{class_defs}result = 'unmatched'\nvalue = {value_code}\n{branches}\n"

    def to_trace_if_code(self, value_codes: list[str] | None = None) -> str:
        class_defs = self.class_defs_code()
        values = value_codes or self.sample_value_codes()
        value_lines = "\n".join(f"    {value_code}," for value_code in values)
        branch_blocks = []
        for index, case in enumerate(self.cases):
            if isinstance(case.pattern, WildcardPattern):
                branch_blocks.append(f"    else:\n        print({case.body!r})")
                continue
            keyword = "if" if index == 0 else "elif"
            condition = case.pattern.to_condition_code("value", safe=True)
            body = indent_code(case.trace_body_code("value", index), "        ")
            branch_blocks.append(f"    {keyword} {condition}:\n{body}")
        branches = "\n".join(branch_blocks)
        return f"{class_defs}values = [\n{value_lines}\n]\nfor value in values:\n{branches}\n"

    def sample_value_codes(self) -> list[str]:
        values = []
        for case in self.cases:
            if isinstance(case.pattern, WildcardPattern):
                continue
            values.extend(
                bounded_sample_values(
                    [
                        *matching_value_codes(case.pattern),
                        *fallthrough_value_codes(case.pattern),
                    ]
                )
            )
        values.append("object()")
        return values


def bounded_sample_values(values: list[str]) -> list[str]:
    if len(values) <= MAX_SAMPLE_VALUES_PER_CASE:
        return values
    if MAX_SAMPLE_VALUES_PER_CASE <= 1:
        return values[:MAX_SAMPLE_VALUES_PER_CASE]

    last_index = len(values) - 1
    return [
        values[round(index * last_index / (MAX_SAMPLE_VALUES_PER_CASE - 1))]
        for index in range(MAX_SAMPLE_VALUES_PER_CASE)
    ]


def matching_value_codes(pattern: GeneratedPattern) -> list[str]:
    if isinstance(pattern, OrPattern):
        if or_alternatives_have_compatible_captures(pattern):
            return [
                value
                for alternative in pattern.alternatives
                for value in matching_value_codes(alternative)
            ]
        return [pattern.to_value_code()]
    if isinstance(pattern, ClassPattern):
        return class_matching_value_codes(pattern.class_name, pattern.attrs)
    if isinstance(pattern, ClassUnionPattern):
        return [
            value
            for class_name in pattern.class_names
            for value in class_matching_value_codes(class_name, pattern.attrs)
        ]
    if isinstance(pattern, SequenceCapturePattern):
        return [pattern.to_value_code()]
    if isinstance(pattern, SequencePattern):
        return sequence_matching_value_codes(
            pattern.elements, tuple_value=pattern.tuple_value
        )
    if isinstance(pattern, GappedSequencePattern):
        return sequence_matching_value_codes(
            pattern.elements, tuple_value=pattern.tuple_value
        )
    if isinstance(pattern, StarSequencePattern):
        return sequence_matching_value_codes(
            pattern.elements, append_extra=True, tuple_value=pattern.tuple_value
        )
    if isinstance(pattern, GappedStarSequencePattern):
        return sequence_matching_value_codes(
            pattern.elements, append_extra=True, tuple_value=pattern.tuple_value
        )
    return [pattern.to_value_code()]


def class_matching_value_codes(
    class_name: str, attrs: tuple[tuple[str, GeneratedPattern], ...]
) -> list[str]:
    return class_value_codes_from_expansion(
        class_name,
        attrs,
        matching_value_codes,
        expand_single_value=False,
        include_unexpanded_value=True,
    )


def class_value_codes_from_expansion(
    class_name: str,
    attrs: tuple[tuple[str, GeneratedPattern], ...],
    expand_pattern: "ValueExpander",
    expand_single_value: bool,
    include_unexpanded_value: bool,
) -> list[str]:
    if include_unexpanded_value and not expand_single_value:
        attr_options = [
            (attr, expand_pattern(pattern) or [pattern.to_value_code()])
            for attr, pattern in sorted(attrs, key=class_attr_sort_key)
        ]
        if not attr_options:
            return [class_value_code(class_name, [])]
        return [
            class_value_code(
                class_name,
                [f"{attr}={value}" for (attr, _), value in zip(attr_options, values)],
            )
            for values in product(*(values for _, values in attr_options))
        ]

    attr_values = []
    for index, (attr, pattern) in enumerate(sorted(attrs, key=class_attr_sort_key)):
        values = expand_pattern(pattern)
        if values and (expand_single_value or len(values) > 1):
            return [
                class_value_code(
                    class_name,
                    [
                        *attr_values,
                        f"{attr}={value}",
                        *matching_attrs_after_index(attrs, index),
                    ],
                )
                for value in values
            ]
        if values:
            attr_values.append(f"{attr}={values[0]}")
        else:
            attr_values.append(f"{attr}={pattern.to_value_code()}")
    if include_unexpanded_value:
        return [class_value_code(class_name, attr_values)]
    return []


def class_value_code(class_name: str, attr_values: list[str]) -> str:
    if not attr_values:
        return f"{class_name}()"
    return f"{class_name}({', '.join(attr_values)})"


def sequence_matching_value_codes(
    elements: tuple[GeneratedPattern | None, ...],
    append_extra: bool = False,
    tuple_value: bool = False,
) -> list[str]:
    return sequence_value_codes_from_expansion(
        elements,
        matching_value_codes,
        expand_single_value=False,
        include_unexpanded_value=True,
        append_extra=append_extra,
        tuple_value=tuple_value,
    )


ValueExpander = Callable[[GeneratedPattern], list[str]]


def sequence_value_codes_from_expansion(
    elements: tuple[GeneratedPattern | None, ...],
    expand_pattern: "ValueExpander",
    expand_single_value: bool,
    include_unexpanded_value: bool,
    append_extra: bool = False,
    tuple_value: bool = False,
) -> list[str]:
    if include_unexpanded_value and not expand_single_value:
        element_options = [
            (
                ["object()"]
                if element is None
                else expand_pattern(element) or [element.to_value_code()]
            )
            for element in elements
        ]
        if append_extra:
            element_options.append(["object()"])
        return [
            sequence_value_code(
                ", ".join(values),
                tuple_value=tuple_value,
                element_count=len(values),
            )
            for values in product(*element_options)
        ]

    element_values = []
    for element in elements:
        if element is None:
            element_values.append("object()")
            continue

        values = expand_pattern(element)
        if values and (expand_single_value or len(values) > 1):
            suffix = matching_sequence_suffix_after(elements, len(element_values))
            if append_extra:
                suffix.append("object()")
            return [
                sequence_value_code(
                    ", ".join([*element_values, value, *suffix]),
                    tuple_value=tuple_value,
                    element_count=len(element_values) + len(suffix) + 1,
                )
                for value in values
            ]
        element_values.append(element.to_value_code())

    if append_extra:
        element_values.append("object()")
    if include_unexpanded_value:
        return [
            sequence_value_code(
                ", ".join(element_values),
                tuple_value=tuple_value,
                element_count=len(element_values),
            )
        ]
    return []


def fallthrough_value_codes(pattern: GeneratedPattern) -> list[str]:
    if isinstance(pattern, OrPattern):
        if or_alternatives_have_shared_captures(pattern):
            return [
                value
                for alternative in pattern.alternatives
                for value in fallthrough_value_codes(alternative)
            ]
        disjoint_values = disjoint_or_fallthrough_value_codes(pattern)
        if disjoint_values is not None:
            return disjoint_values
        return []
    if isinstance(pattern, LiteralPattern):
        return [mismatching_literal(pattern.value)]
    if isinstance(pattern, AttributeGuardedClassPattern):
        return [
            f"{pattern.class_name}({pattern.attr}={mismatching_literal(pattern.value)})"
        ]
    if isinstance(pattern, RelationalGuardedClassPattern):
        return [f"{pattern.class_name}({pattern.attr}={pattern.fallthrough_value})"]
    if isinstance(pattern, CaptureClassPattern):
        elements = ", ".join(
            "object()" for _ in range(max(pattern.required_length() - 1, 0))
        )
        return [f"{pattern.class_name}({pattern.attr}=[{elements}])"]
    if isinstance(pattern, SequenceCapturePattern):
        elements = ", ".join(
            "object()" for _ in range(max(pattern.required_length() - 1, 0))
        )
        return [
            sequence_value_code(
                elements,
                tuple_value=pattern.tuple_value,
                element_count=max(pattern.required_length() - 1, 0),
            )
        ]
    if isinstance(pattern, GuardedPattern):
        return fallthrough_value_codes(pattern.pattern)
    if isinstance(pattern, ClassPattern):
        return class_fallthrough_value_codes(pattern.class_name, pattern.attrs)
    if isinstance(pattern, ClassUnionPattern):
        return [
            value
            for class_name in pattern.class_names
            for value in class_fallthrough_value_codes(class_name, pattern.attrs)
        ]
    if isinstance(pattern, SequencePattern):
        return sequence_fallthrough_value_codes(
            pattern.elements, tuple_value=pattern.tuple_value
        )
    if isinstance(pattern, GappedSequencePattern):
        return sequence_fallthrough_value_codes(
            pattern.elements, tuple_value=pattern.tuple_value
        )
    if isinstance(pattern, StarSequencePattern):
        return sequence_fallthrough_value_codes(
            pattern.elements, append_extra=True, tuple_value=pattern.tuple_value
        )
    if isinstance(pattern, GappedStarSequencePattern):
        return sequence_fallthrough_value_codes(
            pattern.elements, append_extra=True, tuple_value=pattern.tuple_value
        )
    return []


def or_alternatives_have_compatible_captures(pattern: OrPattern) -> bool:
    signatures = [
        capture_signature(alternative) for alternative in pattern.alternatives
    ]
    return bool(signatures) and all(
        signature == signatures[0] for signature in signatures[1:]
    )


def or_alternatives_have_shared_captures(pattern: OrPattern) -> bool:
    signatures = [
        capture_signature(alternative) for alternative in pattern.alternatives
    ]
    return (
        bool(signatures)
        and signatures[0] != ()
        and all(signature == signatures[0] for signature in signatures[1:])
    )


def disjoint_or_fallthrough_value_codes(pattern: OrPattern) -> list[str] | None:
    if any(contains_capture(alternative) for alternative in pattern.alternatives):
        return None

    class_names = []
    has_value_alternative = False
    for alternative in pattern.alternatives:
        if pattern_is_literal_or_singleton(alternative):
            has_value_alternative = True
            continue
        names = pattern_class_names(alternative)
        if not names:
            return None
        class_names.append(names)

    seen: set[str] = set()
    for names in class_names:
        if seen & names:
            return None
        seen.update(names)

    values = ["object()"] if has_value_alternative else []
    values.extend(
        value
        for alternative in pattern.alternatives
        if pattern_class_names(alternative)
        for value in fallthrough_value_codes(alternative)
    )
    return values or None


def pattern_is_literal_or_singleton(pattern: GeneratedPattern) -> bool:
    if isinstance(pattern, (LiteralPattern, SingletonPattern)):
        return True
    if isinstance(pattern, GuardedPattern):
        return pattern_is_literal_or_singleton(pattern.pattern)
    return False


def pattern_class_names(pattern: GeneratedPattern) -> set[str]:
    if isinstance(pattern, ClassPattern):
        return {pattern.class_name}
    if isinstance(pattern, ClassUnionPattern):
        return set(pattern.class_names)
    if isinstance(pattern, GuardedPattern):
        return pattern_class_names(pattern.pattern)
    return set()


def class_fallthrough_value_codes(
    class_name: str, attrs: tuple[tuple[str, GeneratedPattern], ...]
) -> list[str]:
    return class_value_codes_from_expansion(
        class_name,
        attrs,
        fallthrough_value_codes,
        expand_single_value=True,
        include_unexpanded_value=False,
    )


def matching_attrs_after_index(
    attrs: tuple[tuple[str, GeneratedPattern], ...], current_index: int
) -> list[str]:
    return [
        f"{attr}={pattern.to_value_code()}"
        for attr, pattern in sorted(attrs, key=class_attr_sort_key)[current_index + 1 :]
    ]


def sequence_fallthrough_value_codes(
    elements: tuple[GeneratedPattern | None, ...],
    append_extra: bool = False,
    tuple_value: bool = False,
) -> list[str]:
    return sequence_value_codes_from_expansion(
        elements,
        fallthrough_value_codes,
        expand_single_value=True,
        include_unexpanded_value=False,
        append_extra=append_extra,
        tuple_value=tuple_value,
    )


def matching_sequence_suffix_after(
    elements: tuple[GeneratedPattern | None, ...], current_index: int
) -> list[str]:
    return [
        "object()" if element is None else element.to_value_code()
        for element in elements[current_index + 1 :]
    ]


def mismatching_literal(value: str) -> str:
    if value == "'ready'":
        return "'miss'"
    return "0" if value != "0" else "1"


def generated_programs(count: int, seed: int) -> list[GeneratedProgram]:
    rng = random.Random(seed)
    return [generate_program(rng) for _ in range(count)]


def generate_program(rng: random.Random) -> GeneratedProgram:
    program = generate_program_candidate(rng)
    for _ in range(99):
        if sample_values_cover_reachable_cases(program):
            return program
        program = generate_program_candidate(rng)
    return program


def generate_program_candidate(rng: random.Random) -> GeneratedProgram:
    class_pool = ("Point", "Token", "Node")
    class_count = rng.randint(1, len(class_pool))
    classes = class_pool[:class_count]
    branches = rng.randint(2, 5)
    cases = [
        GeneratedCase(generate_pattern(rng, classes, depth=5), f"branch_{index}")
        for index in range(branches)
    ]
    if rng.choice([True, False]):
        cases.append(GeneratedCase(WildcardPattern(), "default"))
    return GeneratedProgram(classes=classes, cases=tuple(cases))


def sample_values_cover_reachable_cases(program: GeneratedProgram) -> bool:
    _, output, error = execute_result(program.to_trace_if_code())
    if error is not None:
        return False

    reached = set(output.splitlines())
    required = {
        case.body
        for case in program.cases
        if not is_constructed_as_unreachable(case.pattern)
    }
    return required <= reached


def is_constructed_as_unreachable(pattern: GeneratedPattern) -> bool:
    if isinstance(pattern, GuardedPattern):
        return pattern.guard == "False" or is_constructed_as_unreachable(
            pattern.pattern
        )
    if isinstance(pattern, OrPattern):
        return all(
            is_constructed_as_unreachable(alternative)
            for alternative in pattern.alternatives
        )
    if isinstance(pattern, (ClassPattern, ClassUnionPattern)):
        return any(
            is_constructed_as_unreachable(attr_pattern)
            for _, attr_pattern in pattern.attrs
        )
    if isinstance(pattern, SequencePattern):
        return any(
            is_constructed_as_unreachable(element) for element in pattern.elements
        )
    if isinstance(pattern, GappedSequencePattern):
        return any(
            element is not None and is_constructed_as_unreachable(element)
            for element in pattern.elements
        )
    if isinstance(pattern, StarSequencePattern):
        return any(
            is_constructed_as_unreachable(element) for element in pattern.elements
        )
    if isinstance(pattern, GappedStarSequencePattern):
        return any(
            element is not None and is_constructed_as_unreachable(element)
            for element in pattern.elements
        )
    return False


def generate_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    choices = [
        "literal",
        "singleton",
        "or_literal",
        "class",
        "attribute_guarded_class",
        "relational_guarded_class",
        "capture_class",
        "sequence_capture",
        "or_sequence_capture",
        "class_attribute_or_sequence_capture",
        "guarded",
        "sequence",
        "gapped_sequence",
        "star",
        "gapped_star",
    ]
    if len(classes) > 1:
        choices.append("common_guarded_or")
        choices.append("common_guarded_or_capture")
        choices.append("or_capture")
        choices.append("class_union_sequence_capture")
        if depth > 0:
            choices.append("nested_or_capture")
    if depth > 0:
        choices.extend(["nested_class", "nested_sequence"])
    kind = rng.choice(choices)

    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_pattern(rng, classes)
    if kind == "common_guarded_or":
        return generate_common_guarded_or_pattern(rng, classes, depth=depth)
    if kind == "common_guarded_or_capture":
        return generate_common_guarded_or_capture_pattern(rng, classes)
    if kind == "or_capture":
        return generate_or_capture_pattern(rng, classes)
    if kind == "class_union_sequence_capture":
        return generate_class_union_sequence_capture_pattern(rng, classes)
    if kind == "nested_or_capture":
        return generate_nested_or_capture_pattern(rng, classes, depth=depth)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=0)
    if kind == "attribute_guarded_class":
        return generate_attribute_guarded_class_pattern(rng, classes)
    if kind == "relational_guarded_class":
        return generate_relational_guarded_class_pattern(rng, classes)
    if kind == "capture_class":
        return generate_capture_class_pattern(rng, classes)
    if kind == "sequence_capture":
        return generate_sequence_capture_pattern(rng)
    if kind == "or_sequence_capture":
        return generate_or_sequence_capture_pattern(rng)
    if kind == "class_attribute_or_sequence_capture":
        return generate_class_attribute_or_sequence_capture_pattern(rng, classes)
    if kind == "guarded":
        return generate_guarded_pattern(rng, classes, depth=depth)
    if kind == "nested_class":
        return generate_class_pattern(rng, classes, depth=depth)
    if kind == "nested_sequence":
        return generate_sequence_pattern(
            rng, classes, depth=depth, bracketed=False, allow_nested_sequence=True
        )
    if kind == "gapped_sequence":
        return generate_gapped_sequence_pattern(
            rng, classes, depth=depth, bracketed=False
        )
    if kind == "star":
        return generate_star_sequence_pattern(rng, classes, depth=depth)
    if kind == "gapped_star":
        return generate_gapped_star_sequence_pattern(rng, classes, depth=depth)

    return generate_sequence_pattern(
        rng, classes, depth=0, bracketed=False, allow_nested_sequence=False
    )


def generate_class_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> ClassPattern | ClassUnionPattern:
    class_name = rng.choice(classes)
    attrs = rng.sample(["x", "y", "kind"], rng.randint(0, 2))
    attr_patterns = tuple(
        (attr, generate_attribute_pattern(rng, classes, depth)) for attr in attrs
    )
    if len(classes) > 1 and rng.choice([True, False]):
        class_names = tuple(rng.sample(classes, rng.randint(2, len(classes))))
        return ClassUnionPattern(class_names, attr_patterns)
    return ClassPattern(class_name, attr_patterns)


def generate_attribute_guarded_class_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> AttributeGuardedClassPattern:
    class_name = rng.choice(classes)
    attr = rng.choice(["x", "y", "kind"])
    guard_expr, value = rng.choice(
        [
            ("len([None])", "1"),
            ("len([None, None])", "2"),
            ("str('ready')", "'ready'"),
            ("f'ready'", "'ready'"),
        ]
    )
    return AttributeGuardedClassPattern(class_name, attr, guard_expr, value)


def generate_relational_guarded_class_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> RelationalGuardedClassPattern:
    class_name = rng.choice(classes)
    attr = rng.choice(["x", "y", "kind"])
    operator, threshold, value, fallthrough_value = rng.choice(
        [
            (">", "0", "1", "0"),
            (">=", "1", "1", "0"),
            ("<", "2", "1", "2"),
            ("<=", "1", "1", "2"),
            ("!=", "0", "1", "0"),
        ]
    )
    return RelationalGuardedClassPattern(
        class_name, attr, operator, threshold, value, fallthrough_value
    )


def generate_capture_class_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> CaptureClassPattern:
    class_name = rng.choice(classes)
    attr = rng.choice(["x", "y", "items"])
    capture_indices = generate_capture_indices(rng)
    return CaptureClassPattern(class_name, attr, capture_indices)


def generate_capture_indices(rng: random.Random) -> tuple[int, ...]:
    length = rng.randint(1, 3)
    capture_indices = [index for index in range(length) if rng.choice([True, False])]
    if not capture_indices:
        capture_indices = [rng.randrange(length)]
    if rng.choice([True, False, False]):
        capture_indices.insert(
            rng.randrange(len(capture_indices) + 1), rng.choice(capture_indices)
        )
    return tuple(capture_indices)


def generate_sequence_capture_pattern(rng: random.Random) -> SequenceCapturePattern:
    checked_index = rng.randint(0, 2)
    available_capture_indices = [index for index in range(3) if index != checked_index]
    capture_count = rng.randint(1, len(available_capture_indices))
    capture_indices = tuple(rng.sample(available_capture_indices, capture_count))
    if rng.choice([True, False, False]):
        capture_indices = (
            *capture_indices,
            rng.choice(capture_indices),
        )
    return SequenceCapturePattern(
        checked_index=checked_index,
        checked_pattern=generate_literal_or_singleton(rng),
        capture_indices=capture_indices,
        tuple_value=rng.choice([True, False]),
    )


def generate_or_sequence_capture_pattern(rng: random.Random) -> OrPattern:
    checked_index = rng.randint(0, 2)
    available_capture_indices = [index for index in range(3) if index != checked_index]
    capture_indices = tuple(
        rng.sample(
            available_capture_indices, rng.randint(1, len(available_capture_indices))
        )
    )
    values = rng.sample(
        ["-3.5", "-1", "0", "+1", "2", "+3.5", "'red'", "'blue'", "None", "False"],
        rng.randint(2, 4),
    )
    tuple_value = rng.choice([True, False])
    return OrPattern(
        tuple(
            SequenceCapturePattern(
                checked_index=checked_index,
                checked_pattern=pattern_from_literal_or_singleton(value),
                capture_indices=capture_indices,
                tuple_value=tuple_value,
            )
            for value in values
        )
    )


def generate_class_attribute_or_sequence_capture_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> ClassPattern:
    return ClassPattern(
        rng.choice(classes),
        ((rng.choice(["x", "y", "items"]), generate_or_sequence_capture_pattern(rng)),),
    )


def generate_class_union_sequence_capture_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> ClassPattern:
    return ClassPattern(
        rng.choice(classes),
        (
            (
                rng.choice(["x", "y", "items"]),
                ClassUnionPattern(
                    tuple(rng.sample(classes, rng.randint(2, len(classes)))),
                    (
                        (
                            rng.choice(["x", "y", "items"]),
                            generate_sequence_capture_pattern(rng),
                        ),
                    ),
                ),
            ),
        ),
    )


def generate_guarded_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GuardedPattern:
    choices = [
        "literal",
        "singleton",
        "or_literal",
        "class",
        "attribute_guarded_class",
        "relational_guarded_class",
        "capture_class",
        "sequence_capture",
        "sequence",
        "gapped_sequence",
        "star",
        "gapped_star",
    ]
    if len(classes) > 1:
        choices.append("common_guarded_or")
        choices.append("common_guarded_or_capture")
        choices.append("or_capture")
        choices.append("class_union_sequence_capture")
        if depth > 1:
            choices.append("nested_or_capture")
    kind = rng.choice(choices)
    if kind == "literal":
        pattern: GeneratedPattern = LiteralPattern(generate_literal(rng))
    elif kind == "singleton":
        pattern = SingletonPattern(rng.choice(["None", "True", "False"]))
    elif kind == "or_literal":
        pattern = generate_or_literal_pattern(rng)
    elif kind == "common_guarded_or":
        pattern = generate_common_guarded_or_pattern(rng, classes, depth=depth)
    elif kind == "common_guarded_or_capture":
        pattern = generate_common_guarded_or_capture_pattern(rng, classes)
    elif kind == "class":
        pattern = generate_class_pattern(rng, classes, depth=depth)
    elif kind == "attribute_guarded_class":
        pattern = generate_attribute_guarded_class_pattern(rng, classes)
    elif kind == "relational_guarded_class":
        pattern = generate_relational_guarded_class_pattern(rng, classes)
    elif kind == "capture_class":
        pattern = generate_capture_class_pattern(rng, classes)
    elif kind == "sequence_capture":
        pattern = generate_sequence_capture_pattern(rng)
    elif kind == "or_capture":
        pattern = generate_or_capture_pattern(rng, classes)
    elif kind == "nested_or_capture":
        pattern = generate_nested_or_capture_pattern(rng, classes, depth=depth)
    elif kind == "gapped_sequence":
        pattern = generate_gapped_sequence_pattern(
            rng, classes, depth=depth, bracketed=False
        )
    elif kind == "star":
        pattern = generate_star_sequence_pattern(rng, classes, depth=depth)
    elif kind == "gapped_star":
        pattern = generate_gapped_star_sequence_pattern(rng, classes, depth=depth)
    else:
        pattern = generate_sequence_pattern(
            rng, classes, depth=depth, bracketed=False, allow_nested_sequence=True
        )

    return GuardedPattern(
        pattern,
        generate_guard_expression(rng),
    )


def generate_guard_expression(rng: random.Random) -> str:
    return rng.choice(
        [
            "True",
            "not False",
            "(True or False)",
            "len([None]) == 1",
            "bool([None])",
            "(1 < 2 and 'x'.islower())",
            "((guard_value := 1) == 1)",
            "{subject} is not None",
            "not isinstance({subject}, dict)",
            "False",
        ]
    )


def generate_reachable_guard_expression(rng: random.Random) -> str:
    return rng.choice(
        [
            "True",
            "not False",
            "(True or False)",
            "len([None]) == 1",
            "bool([None])",
            "(1 < 2 and 'x'.islower())",
            "((guard_value := 1) == 1)",
            "not isinstance({subject}, dict)",
            "hasattr({subject}, '__class__')",
        ]
    )


def generate_attribute_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    if depth <= 0:
        return generate_literal_or_singleton(rng)
    choices = [
        "literal",
        "singleton",
        "or_literal",
        "class",
        "attribute_guarded_class",
        "relational_guarded_class",
        "capture_class",
        "sequence_capture",
        "guarded",
        "sequence",
        "gapped_sequence",
        "star",
        "gapped_star",
    ]
    if len(classes) > 1:
        choices.append("common_guarded_or")
        choices.append("common_guarded_or_capture")
        choices.append("or_capture")
        if depth > 1:
            choices.append("nested_or_capture")
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "common_guarded_or":
        return generate_common_guarded_or_pattern(rng, classes, depth=depth - 1)
    if kind == "common_guarded_or_capture":
        return generate_common_guarded_or_capture_pattern(rng, classes)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=depth - 1)
    if kind == "attribute_guarded_class":
        return generate_attribute_guarded_class_pattern(rng, classes)
    if kind == "relational_guarded_class":
        return generate_relational_guarded_class_pattern(rng, classes)
    if kind == "capture_class":
        return generate_capture_class_pattern(rng, classes)
    if kind == "sequence_capture":
        return generate_sequence_capture_pattern(rng)
    if kind == "or_capture":
        return generate_or_capture_pattern(rng, classes)
    if kind == "class_union_sequence_capture":
        return generate_class_union_sequence_capture_pattern(rng, classes)
    if kind == "nested_or_capture":
        return generate_nested_or_capture_pattern(rng, classes, depth=depth - 1)
    if kind == "guarded":
        return GuardedPattern(
            generate_attribute_pattern(rng, classes, depth=depth - 1),
            generate_reachable_guard_expression(rng),
        )
    if kind == "gapped_sequence":
        return generate_gapped_sequence_pattern(
            rng, classes, depth=depth - 1, bracketed=True
        )
    if kind == "star":
        return generate_star_sequence_pattern(rng, classes, depth=depth - 1)
    if kind == "gapped_star":
        return generate_gapped_star_sequence_pattern(rng, classes, depth=depth - 1)
    return generate_sequence_pattern(
        rng, classes, depth - 1, bracketed=True, allow_nested_sequence=True
    )


def generate_sequence_pattern(
    rng: random.Random,
    classes: tuple[str, ...],
    depth: int,
    bracketed: bool,
    allow_nested_sequence: bool,
) -> SequencePattern:
    elements = tuple(
        generate_sequence_element_pattern(rng, classes, depth, allow_nested_sequence)
        for _ in range(rng.randint(1, 3))
    )
    return SequencePattern(
        elements, bracketed=bracketed, tuple_value=rng.choice([True, False])
    )


def generate_gapped_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int, bracketed: bool
) -> GappedSequencePattern:
    length = rng.randint(2, 5)
    checked_indices = generate_checked_indices(rng, length)
    elements = tuple(
        (
            generate_sequence_element_pattern(
                rng, classes, depth, allow_nested_sequence=True
            )
            if index in checked_indices
            else None
        )
        for index in range(length)
    )
    return GappedSequencePattern(
        elements, bracketed=bracketed, tuple_value=rng.choice([True, False])
    )


def generate_checked_indices(rng: random.Random, length: int) -> set[int]:
    while True:
        checked_indices = {
            index for index in range(length) if rng.choice([True, False])
        }
        if not checked_indices:
            continue
        if max_consecutive_gaps(checked_indices, length) < 3:
            return checked_indices


def max_consecutive_gaps(checked_indices: set[int], length: int) -> int:
    longest = 0
    current = 0
    for index in range(length):
        if index in checked_indices:
            current = 0
            continue
        current += 1
        longest = max(longest, current)
    return longest


def generate_star_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> StarSequencePattern:
    elements = tuple(
        generate_sequence_element_pattern(
            rng, classes, depth, allow_nested_sequence=True
        )
        for _ in range(rng.randint(1, 3))
    )
    return StarSequencePattern(elements, tuple_value=rng.choice([True, False]))


def generate_gapped_star_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GappedStarSequencePattern:
    length = rng.randint(2, 5)
    checked_indices = generate_checked_indices(rng, length)
    elements = tuple(
        (
            generate_sequence_element_pattern(
                rng, classes, depth, allow_nested_sequence=True
            )
            if index in checked_indices
            else None
        )
        for index in range(length)
    )
    return GappedStarSequencePattern(elements, tuple_value=rng.choice([True, False]))


def generate_sequence_element_pattern(
    rng: random.Random,
    classes: tuple[str, ...],
    depth: int,
    allow_nested_sequence: bool,
) -> GeneratedPattern:
    """Generate only sequence elements Matchify can currently reconstruct."""
    if depth <= 0:
        return generate_literal_or_singleton(rng)

    choices = [
        "literal",
        "singleton",
        "or_literal",
        "class",
        "attribute_guarded_class",
        "relational_guarded_class",
        "capture_class",
        "sequence_capture",
        "guarded",
    ]
    if len(classes) > 1:
        choices.append("common_guarded_or")
        choices.append("common_guarded_or_capture")
        choices.append("or_class")
        choices.append("or_class_attribute")
        choices.append("or_nested_class_attribute")
        choices.append("or_capture")
        choices.append("class_union_sequence_capture")
        choices.append("class_union")
        choices.append("nested_class_union")
        if depth > 1:
            choices.append("nested_or_capture")
    if allow_nested_sequence:
        choices.extend(["sequence", "gapped_sequence", "star", "gapped_star"])
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "common_guarded_or":
        return generate_common_guarded_or_pattern(rng, classes, depth=depth - 1)
    if kind == "common_guarded_or_capture":
        return generate_common_guarded_or_capture_pattern(rng, classes)
    if kind == "or_class":
        return generate_or_class_pattern(rng, classes)
    if kind == "or_class_attribute":
        return generate_or_class_attribute_pattern(rng, classes)
    if kind == "or_nested_class_attribute":
        return generate_or_nested_class_attribute_pattern(rng, classes)
    if kind == "or_capture":
        return generate_or_capture_pattern(rng, classes)
    if kind == "class_union_sequence_capture":
        return generate_class_union_sequence_capture_pattern(rng, classes)
    if kind == "class_union":
        return generate_sequence_element_class_union_pattern(rng, classes)
    if kind == "nested_class_union":
        return generate_sequence_element_nested_class_union_pattern(
            rng, classes, depth=depth - 1
        )
    if kind == "nested_or_capture":
        return generate_nested_or_capture_pattern(rng, classes, depth=depth - 1)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=depth - 1)
    if kind == "attribute_guarded_class":
        return generate_attribute_guarded_class_pattern(rng, classes)
    if kind == "relational_guarded_class":
        return generate_relational_guarded_class_pattern(rng, classes)
    if kind == "capture_class":
        return generate_capture_class_pattern(rng, classes)
    if kind == "sequence_capture":
        return generate_sequence_capture_pattern(rng)
    if kind == "guarded":
        return GuardedPattern(
            generate_sequence_element_pattern(
                rng,
                classes,
                depth=depth - 1,
                allow_nested_sequence=allow_nested_sequence,
            ),
            generate_reachable_guard_expression(rng),
        )
    if kind == "gapped_sequence":
        return generate_gapped_sequence_pattern(
            rng, classes, depth=depth - 1, bracketed=True
        )
    if kind == "star":
        return generate_star_sequence_pattern(rng, classes, depth=depth - 1)
    if kind == "gapped_star":
        return generate_gapped_star_sequence_pattern(rng, classes, depth=depth - 1)
    return generate_sequence_pattern(
        rng,
        classes,
        depth - 1,
        bracketed=True,
        allow_nested_sequence=True,
    )


def pattern_from_literal_or_singleton(value: str) -> LiteralPattern | SingletonPattern:
    if value in {"None", "True", "False"}:
        return SingletonPattern(value)
    return LiteralPattern(value)


def sequence_value_code(elements: str, tuple_value: bool, element_count: int) -> str:
    if not tuple_value:
        return f"[{elements}]"
    if element_count != 1:
        return f"({elements})"
    return f"({elements},)"


def generate_or_literal_pattern(rng: random.Random) -> OrPattern:
    values = rng.sample(
        [
            "-3.5",
            "-1",
            "0",
            "+1",
            "2",
            "+3.5",
            "'red'",
            "'blue'",
            "'ready'",
            "None",
            "False",
        ],
        rng.randint(2, 4),
    )
    return OrPattern(
        tuple(pattern_from_literal_or_singleton(value) for value in values)
    )


def generate_or_pattern(rng: random.Random, classes: tuple[str, ...]) -> OrPattern:
    alternatives = tuple(
        generate_or_safe_pattern(rng, classes, depth=4)
        for _ in range(rng.randint(2, 4))
    )
    return OrPattern(alternatives)


def generate_common_guarded_or_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> OrPattern:
    guard = rng.choice(
        ["True", "not False", "(True or False)", "{subject} is not None"]
    )
    alternatives = tuple(
        GuardedPattern(generate_or_safe_pattern(rng, classes, depth=depth), guard)
        for _ in range(rng.randint(2, 4))
    )
    return OrPattern(alternatives)


def generate_common_guarded_or_capture_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> OrPattern:
    guard = rng.choice(["True", "not False", "{subject} is not None"])
    capture_pattern = generate_or_capture_pattern(rng, classes)
    return OrPattern(
        tuple(
            GuardedPattern(alternative, guard)
            for alternative in capture_pattern.alternatives
        )
    )


def generate_or_class_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> OrPattern:
    return OrPattern(
        tuple(
            ClassPattern(class_name)
            for class_name in rng.sample(classes, rng.randint(2, len(classes)))
        )
    )


def generate_or_class_attribute_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> OrPattern:
    attr = rng.choice(["x", "y", "kind"])
    return OrPattern(
        tuple(
            ClassPattern(class_name, ((attr, generate_literal_or_singleton(rng)),))
            for class_name in rng.sample(classes, rng.randint(2, len(classes)))
        )
    )


def generate_or_nested_class_attribute_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> OrPattern:
    attr = rng.choice(["x", "y", "kind"])
    nested_attr = rng.choice(["x", "y", "kind"])
    nested_classes = tuple(rng.sample(classes, rng.randint(1, len(classes))))
    return OrPattern(
        tuple(
            ClassPattern(
                class_name,
                (
                    (
                        attr,
                        ClassPattern(
                            rng.choice(nested_classes),
                            ((nested_attr, generate_literal_or_singleton(rng)),),
                        ),
                    ),
                ),
            )
            for class_name in rng.sample(classes, rng.randint(2, len(classes)))
        )
    )


def generate_sequence_element_class_union_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> ClassUnionPattern:
    class_names = tuple(rng.sample(classes, rng.randint(2, len(classes))))
    attrs = ()
    if rng.choice([True, False]):
        attrs = ((rng.choice(["x", "y", "kind"]), generate_literal_or_singleton(rng)),)
    return ClassUnionPattern(class_names, attrs)


def generate_sequence_element_nested_class_union_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> ClassUnionPattern:
    class_names = tuple(rng.sample(classes, rng.randint(2, len(classes))))
    attr = rng.choice(["x", "y", "kind"])
    nested_attr = rng.choice(["x", "y", "kind"])
    nested_pattern: GeneratedPattern = generate_literal_or_singleton(rng)
    if depth > 0:
        nested_pattern = generate_or_safe_attribute_pattern(
            rng, classes, depth=depth - 1
        )
    return ClassUnionPattern(
        class_names,
        (
            (
                attr,
                ClassPattern(
                    rng.choice(classes),
                    ((nested_attr, nested_pattern),),
                ),
            ),
        ),
    )


def generate_or_capture_pattern(
    rng: random.Random, classes: tuple[str, ...]
) -> OrPattern:
    attr = rng.choice(["x", "y", "items"])
    capture_indices = generate_capture_indices(rng)
    alternatives = tuple(
        CaptureClassPattern(class_name, attr, capture_indices)
        for class_name in rng.sample(classes, rng.randint(2, len(classes)))
    )
    return OrPattern(alternatives)


def generate_nested_or_capture_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> OrPattern:
    outer_attr = rng.choice(["x", "y", "items"])
    capture_indices = generate_capture_indices(rng)
    nested_pattern = generate_nested_capture_tail(
        rng, classes, depth=max(depth, 1), capture_indices=capture_indices
    )
    alternatives = tuple(
        ClassPattern(
            class_name,
            ((outer_attr, nested_pattern),),
        )
        for class_name in rng.sample(classes, rng.randint(2, len(classes)))
    )
    return OrPattern(alternatives)


def generate_nested_capture_tail(
    rng: random.Random,
    classes: tuple[str, ...],
    depth: int,
    capture_indices: tuple[int, ...],
) -> GeneratedPattern:
    class_name = rng.choice(classes)
    attr = rng.choice(["x", "y", "items"])
    if depth <= 1:
        return CaptureClassPattern(class_name, attr, capture_indices)
    return ClassPattern(
        class_name,
        (
            (
                attr,
                generate_nested_capture_tail(
                    rng, classes, depth=depth - 1, capture_indices=capture_indices
                ),
            ),
        ),
    )


def generate_or_safe_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    choices = ["literal", "singleton", "or_literal"]
    if classes:
        choices.append("class")
    if depth > 0:
        choices.extend(["sequence", "gapped_sequence", "star", "gapped_star"])

    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_or_safe_class_pattern(rng, classes, depth=depth)
    if kind == "sequence":
        return generate_or_safe_sequence_pattern(
            rng, classes, depth=depth - 1, bracketed=False
        )
    if kind == "gapped_sequence":
        return generate_or_safe_gapped_sequence_pattern(
            rng, classes, depth=depth - 1, bracketed=False
        )
    if kind == "star":
        return generate_or_safe_star_sequence_pattern(rng, classes, depth=depth - 1)
    if kind == "gapped_star":
        return generate_or_safe_gapped_star_sequence_pattern(
            rng, classes, depth=depth - 1
        )
    raise AssertionError(f"Unhandled OR-safe pattern kind: {kind}")


def generate_or_safe_class_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> ClassPattern | ClassUnionPattern:
    attrs = rng.sample(["x", "y", "kind"], rng.randint(0, 2))
    attr_patterns = tuple(
        (attr, generate_or_safe_attribute_pattern(rng, classes, depth=depth - 1))
        for attr in attrs
    )
    if len(classes) > 1 and rng.choice([True, False]):
        class_names = tuple(rng.sample(classes, rng.randint(2, len(classes))))
        return ClassUnionPattern(class_names, attr_patterns)
    return ClassPattern(rng.choice(classes), attr_patterns)


def generate_or_safe_attribute_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    choices = ["literal", "singleton", "or_literal"]
    if classes and depth > 0:
        choices.append("class")
    if depth > 0:
        choices.extend(["sequence", "gapped_sequence", "star", "gapped_star"])
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_or_safe_class_pattern(rng, classes, depth=depth)
    if kind == "sequence":
        return generate_or_safe_sequence_pattern(
            rng, classes, depth=depth - 1, bracketed=True
        )
    if kind == "gapped_sequence":
        return generate_or_safe_gapped_sequence_pattern(
            rng, classes, depth=depth - 1, bracketed=True
        )
    if kind == "star":
        return generate_or_safe_star_sequence_pattern(rng, classes, depth=depth - 1)
    if kind == "gapped_star":
        return generate_or_safe_gapped_star_sequence_pattern(
            rng, classes, depth=depth - 1
        )
    raise AssertionError(f"Unhandled OR-safe attribute kind: {kind}")


def generate_or_safe_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int, bracketed: bool
) -> SequencePattern:
    elements = tuple(
        generate_or_safe_sequence_element_pattern(rng, classes, depth)
        for _ in range(rng.randint(1, 3))
    )
    return SequencePattern(
        elements, bracketed=bracketed, tuple_value=rng.choice([True, False])
    )


def generate_or_safe_gapped_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int, bracketed: bool
) -> GappedSequencePattern:
    length = rng.randint(2, 5)
    checked_indices = generate_checked_indices(rng, length)
    elements = tuple(
        (
            generate_or_safe_sequence_element_pattern(rng, classes, depth)
            if index in checked_indices
            else None
        )
        for index in range(length)
    )
    return GappedSequencePattern(
        elements, bracketed=bracketed, tuple_value=rng.choice([True, False])
    )


def generate_or_safe_star_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> StarSequencePattern:
    elements = tuple(
        generate_or_safe_sequence_element_pattern(rng, classes, depth)
        for _ in range(rng.randint(1, 3))
    )
    return StarSequencePattern(elements, tuple_value=rng.choice([True, False]))


def generate_or_safe_gapped_star_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GappedStarSequencePattern:
    length = rng.randint(2, 5)
    checked_indices = generate_checked_indices(rng, length)
    elements = tuple(
        (
            generate_or_safe_sequence_element_pattern(rng, classes, depth)
            if index in checked_indices
            else None
        )
        for index in range(length)
    )
    return GappedStarSequencePattern(elements, tuple_value=rng.choice([True, False]))


def generate_or_safe_sequence_element_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    choices = ["or_safe"]
    if len(classes) > 1:
        choices.append("or_class")
        choices.append("or_class_attribute")
        choices.append("or_nested_class_attribute")
        choices.append("class_union")
        choices.append("nested_class_union")

    kind = rng.choice(choices)
    if kind == "or_class":
        return generate_or_class_pattern(rng, classes)
    if kind == "or_class_attribute":
        return generate_or_class_attribute_pattern(rng, classes)
    if kind == "or_nested_class_attribute":
        return generate_or_nested_class_attribute_pattern(rng, classes)
    if kind == "class_union":
        return generate_sequence_element_class_union_pattern(rng, classes)
    if kind == "nested_class_union":
        return generate_sequence_element_nested_class_union_pattern(
            rng, classes, depth=depth - 1
        )
    return generate_or_safe_pattern(rng, classes, depth=depth)


def generate_literal_or_singleton(
    rng: random.Random,
) -> LiteralPattern | SingletonPattern:
    if rng.choice([True, False]):
        return LiteralPattern(generate_literal(rng))
    return SingletonPattern(rng.choice(["None", "True", "False"]))


def generate_literal(rng: random.Random) -> str:
    return rng.choice(
        ["-3.5", "-1", "0", "+1", "2", "+3.5", "'red'", "'blue'", "'ready'"]
    )


def indent_code(code: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else line for line in code.splitlines())


def execute_result(source: str) -> tuple[str, str, type[BaseException] | None]:
    stdout = StringIO()
    stderr = StringIO()
    exception_type = None
    namespace: dict[str, object] = {}
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(source, namespace)
    except BaseException as error:
        exception_type = type(error)
    return (
        str(namespace.get("result")),
        stdout.getvalue() + stderr.getvalue(),
        exception_type,
    )


def assert_matchify_preserves_trace(
    program: GeneratedProgram, tmp_path: Path, *, require_changed: bool = True
) -> bool:
    if_else_code = program.to_trace_if_code()
    path = tmp_path / "generated.py"
    path.write_text(if_else_code, encoding="utf-8")
    expected_trace = execute_result(if_else_code)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert error is None
    if require_changed:
        assert changed is True
    transformed = path.read_text(encoding="utf-8")
    if changed:
        assert " match " in transformed

    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{if_else_code}\n"
        f"Matchified code:\n{transformed}"
    )
    return changed


def test_generated_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(CaptureClassPattern("Point", "x", (0, 2)), "branch_0"),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert "case Point(x=[capture_0_0, _, capture_0_1, *_])" in transformed
    assert "capture_0_0 = value.x[0]" not in transformed
    assert "capture_0_1 = value.x[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_duplicate_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(CaptureClassPattern("Point", "x", (0, 0, 2)), "branch_0"),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_duplicate_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert "case Point(x=[capture_0_0, _, capture_0_2, *_])" in transformed
    assert "capture_0_1 = capture_0_0" in transformed
    assert "capture_0_0 = value.x[0]" not in transformed
    assert "capture_0_1 = value.x[0]" not in transformed
    assert "capture_0_2 = value.x[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_nested_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Data"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (("data", CaptureClassPattern("Data", "items", (0, 2))),),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_nested_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert "case Point(data=Data(items=[capture_0_0, _, capture_0_1, *_]))" in (
        transformed
    )
    assert "capture_0_0 = value.data.items[0]" not in transformed
    assert "capture_0_1 = value.data.items[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_deep_nested_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Node", "Leaf"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        (
                            "x",
                            ClassPattern(
                                "Node",
                                (
                                    (
                                        "y",
                                        SequencePattern(
                                            (
                                                ClassPattern(
                                                    "Leaf",
                                                    (("kind", LiteralPattern("1")),),
                                                ),
                                                SingletonPattern("None"),
                                            ),
                                            bracketed=True,
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.x, Node)" in source
    assert "isinstance(value.x.y[0], Leaf)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_very_deep_nested_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Node", "Leaf"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        (
                            "x",
                            ClassPattern(
                                "Node",
                                (
                                    (
                                        "y",
                                        ClassPattern(
                                            "Leaf",
                                            (
                                                (
                                                    "items",
                                                    SequencePattern(
                                                        (
                                                            ClassPattern(
                                                                "Point",
                                                                (
                                                                    (
                                                                        "kind",
                                                                        LiteralPattern(
                                                                            "1"
                                                                        ),
                                                                    ),
                                                                ),
                                                            ),
                                                            SingletonPattern("False"),
                                                        ),
                                                        bracketed=True,
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.x.y, Leaf)" in source
    assert "isinstance(value.x.y.items[0], Point)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_extremely_deep_nested_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Node", "Leaf"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        (
                            "x",
                            ClassPattern(
                                "Node",
                                (
                                    (
                                        "y",
                                        ClassPattern(
                                            "Leaf",
                                            (
                                                (
                                                    "z",
                                                    ClassPattern(
                                                        "Point",
                                                        (
                                                            (
                                                                "kind",
                                                                LiteralPattern("1"),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.x.y.z, Point)" in source
    assert "value.x.y.z.kind == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_class_union_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                ClassUnionPattern(
                    ("Point", "Token"),
                    (("items", CaptureClassPattern("Data", "values", (0, 2))),),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_union_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case Point(items=Data(values=[capture_0_0, _, capture_0_1, *_])) | "
        "Token(items=Data(values=[capture_0_0, _, capture_0_1, *_]))"
    ) in transformed
    assert "capture_0_0 = value.items.values[0]" not in transformed
    assert "capture_0_1 = value.items.values[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_class_union_samples_cover_all_classes(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                ClassUnionPattern(
                    ("Point", "Token"),
                    (("kind", LiteralPattern("1")),),
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(kind=1)" in source
    assert "Token(kind=1)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_class_union_fallthrough_samples_cover_all_classes(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                ClassUnionPattern(
                    ("Point", "Token"),
                    (
                        (
                            "kind",
                            AttributeGuardedClassPattern(
                                "Data", "value", "len([None])", "1"
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(ClassPattern("Token"), "branch_2"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(kind=Data(value=1))" in source
    assert "Token(kind=Data(value=1))" in source
    assert "Point(kind=Data(value=0))" in source
    assert "Token(kind=Data(value=0))" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_nested_class_union_fallthrough_samples_cover_all_classes(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Wrapper", "Point", "Token"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Wrapper",
                    (
                        (
                            "inner",
                            ClassUnionPattern(
                                ("Point", "Token"),
                                (("kind", LiteralPattern("1")),),
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Wrapper"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Wrapper(inner=Point(kind=1))" in source
    assert "Wrapper(inner=Token(kind=1))" in source
    assert "Wrapper(inner=Point(kind=0))" in source
    assert "Wrapper(inner=Token(kind=0))" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_sequence_union_fallthrough_samples_cover_all_classes(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (
                        ClassUnionPattern(
                            ("Point", "Token"),
                            (("kind", LiteralPattern("1")),),
                        ),
                    ),
                    bracketed=False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "[Point(kind=1)]" in source
    assert "[Token(kind=1)]" in source
    assert "[Point(kind=0)]" in source
    assert "[Token(kind=0)]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_or_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        CaptureClassPattern("Point", "items", (0, 2)),
                        CaptureClassPattern("Token", "items", (0, 2)),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    assert "Point(items=[1, 2, 3, object()])" in source
    assert "Token(items=[1, 2, 3, object()])" in source
    assert "Point(items=[object(), object()])" in source
    assert "Token(items=[object(), object()])" in source
    path = tmp_path / "generated_or_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case Point(items=[capture_0_0, _, capture_0_1, *_]) | "
        "Token(items=[capture_0_0, _, capture_0_1, *_])"
    ) in transformed
    assert "capture_0_0 = value.items[0]" not in transformed
    assert "capture_0_1 = value.items[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_common_guarded_or_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        GuardedPattern(ClassPattern("Point"), "not False"),
                        GuardedPattern(ClassPattern("Token"), "not False"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value, Point) and not False" in source
    assert "isinstance(value, Token) and not False" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_guarded_common_guarded_or_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                GuardedPattern(
                    OrPattern(
                        (
                            GuardedPattern(
                                ClassPattern("Point"), "{subject} is not None"
                            ),
                            GuardedPattern(
                                ClassPattern("Token"), "{subject} is not None"
                            ),
                        )
                    ),
                    "not False",
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value, Point) and value is not None" in source
    assert "isinstance(value, Token) and value is not None" in source
    assert "and not False" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_common_guarded_or_capture_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        GuardedPattern(
                            CaptureClassPattern("Point", "items", (0, 2)),
                            "not False",
                        ),
                        GuardedPattern(
                            CaptureClassPattern("Token", "items", (0, 2)),
                            "not False",
                        ),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "capture_0_0 = value.items[0]" in source
    assert "capture_0_1 = value.items[2]" in source
    assert "and not False" in source
    assert_matchify_preserves_trace(program, tmp_path, require_changed=False) is False


def test_generated_attribute_common_guarded_or_program_survives_matchify(
    tmp_path: Path,
):
    pattern = ClassPattern(
        "Wrapper",
        (
            (
                "data",
                OrPattern(
                    (
                        GuardedPattern(ClassPattern("Point"), "{subject} is not None"),
                        GuardedPattern(ClassPattern("Token"), "{subject} is not None"),
                    )
                ),
            ),
        ),
    )
    program = GeneratedProgram(
        classes=("Wrapper", "Point", "Token"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.data, Point) and value.data is not None" in source
    assert "isinstance(value.data, Token) and value.data is not None" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_sequence_element_common_guarded_or_program_survives_matchify(
    tmp_path: Path,
):
    pattern = SequencePattern(
        (
            OrPattern(
                (
                    GuardedPattern(ClassPattern("Point"), "{subject} is not None"),
                    GuardedPattern(ClassPattern("Token"), "{subject} is not None"),
                )
            ),
        ),
        bracketed=False,
    )
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], Point) and value[0] is not None" in source
    assert "isinstance(value[0], Token) and value[0] is not None" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_nested_or_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token", "Data"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern(
                            "Point",
                            (("data", CaptureClassPattern("Data", "items", (0, 2))),),
                        ),
                        ClassPattern(
                            "Token",
                            (("data", CaptureClassPattern("Data", "items", (0, 2))),),
                        ),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(data=Data(items=[1, 2, 3, object()]))" in source
    assert "Token(data=Data(items=[1, 2, 3, object()]))" in source
    path = tmp_path / "generated_nested_or_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case Point(data=Data(items=[capture_0_0, _, capture_0_1, *_])) | "
        "Token(data=Data(items=[capture_0_0, _, capture_0_1, *_]))"
    ) in transformed
    assert "capture_0_0 = value.data.items[0]" not in transformed
    assert "capture_0_1 = value.data.items[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_nested_or_capture_generator_program_survives_matchify(
    tmp_path: Path,
):
    pattern = OrPattern(
        (
            ClassPattern(
                "Point",
                (("data", CaptureClassPattern("Node", "items", (0, 2))),),
            ),
            ClassPattern(
                "Token",
                (("data", CaptureClassPattern("Node", "items", (0, 2))),),
            ),
        )
    )
    program = GeneratedProgram(
        classes=("Point", "Token", "Node"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "capture_0_0 = value.data.items[0]" in source
    assert "capture_0_1 = value.data.items[2]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_deep_nested_or_capture_program_survives_matchify(
    tmp_path: Path,
):
    pattern = OrPattern(
        (
            ClassPattern(
                "Point",
                (
                    (
                        "data",
                        ClassPattern(
                            "Node",
                            (
                                (
                                    "child",
                                    CaptureClassPattern("Leaf", "items", (0, 2)),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            ClassPattern(
                "Token",
                (
                    (
                        "data",
                        ClassPattern(
                            "Node",
                            (
                                (
                                    "child",
                                    CaptureClassPattern("Leaf", "items", (0, 2)),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    program = GeneratedProgram(
        classes=("Point", "Token", "Node", "Leaf"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "capture_0_0 = value.data.child.items[0]" in source
    assert "capture_0_1 = value.data.child.items[2]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_sequence_element_or_capture_program_survives_matchify(
    tmp_path: Path,
):
    pattern = SequencePattern(
        (
            OrPattern(
                (
                    CaptureClassPattern("Point", "items", (0, 1)),
                    CaptureClassPattern("Token", "items", (0, 1)),
                )
            ),
        ),
        bracketed=False,
    )
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "capture_0_0 = value[0].items[0]" in source
    assert "capture_0_1 = value[0].items[1]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_attribute_or_capture_program_survives_matchify(
    tmp_path: Path,
):
    pattern = ClassPattern(
        "Wrapper",
        (
            (
                "data",
                OrPattern(
                    (
                        CaptureClassPattern("Point", "items", (0, 1)),
                        CaptureClassPattern("Token", "items", (0, 1)),
                    )
                ),
            ),
        ),
    )
    program = GeneratedProgram(
        classes=("Wrapper", "Point", "Token"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "capture_0_0 = value.data.items[0]" in source
    assert "capture_0_1 = value.data.items[1]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_three_way_class_union_sequence_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token", "Node"),
        cases=(
            GeneratedCase(
                ClassUnionPattern(
                    ("Point", "Token", "Node"),
                    (
                        (
                            "x",
                            SequencePattern(
                                (LiteralPattern("+1"), LiteralPattern("-3.5")),
                                bracketed=True,
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value, (Point, Token, Node))" in source
    assert "value.x[0] == +1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_sequence_element_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (CaptureClassPattern("Point", "items", (0, 2)),),
                    bracketed=False,
                ),
                "branch_0",
            ),
            GeneratedCase(LiteralPattern("0"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_sequence_element_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert "case Point(items=[capture_0_0, _, capture_0_1, *_])," in transformed
    assert "capture_0_0 = value[0].items[0]" not in transformed
    assert "capture_0_1 = value[0].items[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_direct_sequence_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                SequenceCapturePattern(
                    checked_index=1,
                    checked_pattern=LiteralPattern("2"),
                    capture_indices=(0, 0, 2),
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_direct_sequence_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert "case capture_0_0, 2, capture_0_2, *_:" in transformed
    assert "capture_0_1 = capture_0_0" in transformed
    assert "capture_0_0 = value[0]" not in transformed
    assert "capture_0_1 = value[0]" not in transformed
    assert "capture_0_2 = value[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_or_direct_sequence_capture_program_survives_matchify(
    tmp_path: Path,
):
    pattern = OrPattern(
        (
            SequenceCapturePattern(
                checked_index=1,
                checked_pattern=LiteralPattern("2"),
                capture_indices=(0, 2),
            ),
            SequenceCapturePattern(
                checked_index=1,
                checked_pattern=LiteralPattern("3"),
                capture_indices=(0, 2),
            ),
        )
    )
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_or_direct_sequence_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case [capture_0_0, 2, capture_0_1, *_] | [capture_0_0, 3, capture_0_1, *_]:"
        in (transformed)
    )
    assert "capture_0_0 = value[0]" not in transformed
    assert "capture_0_1 = value[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_attribute_or_direct_sequence_capture_program_survives_matchify(
    tmp_path: Path,
):
    pattern = ClassPattern(
        "Wrapper",
        (
            (
                "data",
                OrPattern(
                    (
                        SequenceCapturePattern(
                            checked_index=1,
                            checked_pattern=LiteralPattern("2"),
                            capture_indices=(0, 2),
                        ),
                        SequenceCapturePattern(
                            checked_index=1,
                            checked_pattern=LiteralPattern("3"),
                            capture_indices=(0, 2),
                        ),
                    )
                ),
            ),
        ),
    )
    program = GeneratedProgram(
        classes=("Wrapper",),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_attribute_or_direct_sequence_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case Wrapper(data=[capture_0_0, 2, capture_0_1, *_] | "
        "[capture_0_0, 3, capture_0_1, *_]):"
    ) in transformed
    assert "capture_0_0 = value.data[0]" not in transformed
    assert "capture_0_1 = value.data[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_nested_class_union_sequence_capture_program_survives_matchify(
    tmp_path: Path,
):
    pattern = ClassPattern(
        "Outer",
        (
            (
                "child",
                ClassUnionPattern(
                    ("Point", "Token"),
                    (
                        (
                            "items",
                            SequenceCapturePattern(
                                checked_index=1,
                                checked_pattern=LiteralPattern("2"),
                                capture_indices=(0,),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    program = GeneratedProgram(
        classes=("Outer", "Point", "Token"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_nested_class_union_sequence_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case Outer(child=Point(items=[capture_0_0, 2, *_]) | "
        "Token(items=[capture_0_0, 2, *_]))"
    ) in transformed
    assert "capture_0_0 = value.child.items[0]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_sequence_element_class_union_sequence_capture_survives_matchify(
    tmp_path: Path,
):
    pattern = SequencePattern(
        (
            ClassPattern(
                "Outer",
                (
                    (
                        "child",
                        ClassUnionPattern(
                            ("Point", "Token"),
                            (
                                (
                                    "items",
                                    SequenceCapturePattern(
                                        checked_index=1,
                                        checked_pattern=LiteralPattern("2"),
                                        capture_indices=(0,),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            SingletonPattern("None"),
        ),
        bracketed=False,
    )
    program = GeneratedProgram(
        classes=("Outer", "Point", "Token"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_sequence_element_class_union_sequence_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert (
        "case Outer(child=Point(items=[capture_0_0, 2, *_]) | "
        "Token(items=[capture_0_0, 2, *_])), None:"
    ) in transformed
    assert "capture_0_0 = value[0].child.items[0]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_guarded_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(
                    CaptureClassPattern("Point", "items", (0, 2)),
                    "not False",
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )
    source = program.to_trace_if_code()
    path = tmp_path / "generated_guarded_capture.py"
    path.write_text(source, encoding="utf-8")
    expected_trace = execute_result(source)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert "case Point(items=[capture_0_0, _, capture_0_1, *_])" in transformed
    assert "not False" in transformed
    assert "capture_0_0 = value.items[0]" not in transformed
    assert "capture_0_1 = value.items[2]" not in transformed
    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{source}\n"
        f"Matchified code:\n{transformed}"
    )


def test_generated_walrus_guard_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(ClassPattern("Point"), "((guard_value := 1) == 1)"),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "guard_value := 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_guarded_or_capture_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                GuardedPattern(
                    OrPattern(
                        (
                            CaptureClassPattern("Point", "items", (0, 2)),
                            CaptureClassPattern("Token", "items", (0, 2)),
                        )
                    ),
                    "not False",
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "and not False" in source
    assert "capture_0_0 = value.items[0]" in source
    assert "capture_0_1 = value.items[2]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_false_guarded_capture_program_falls_through(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(
                    CaptureClassPattern("Point", "items", (0,)),
                    "False",
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_tuple_sequence_value_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (LiteralPattern("1"), LiteralPattern("2")),
                    bracketed=False,
                    tuple_value=True,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "(1, 2)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_tuple_star_sequence_value_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                StarSequencePattern(
                    (LiteralPattern("1"), LiteralPattern("2")),
                    tuple_value=True,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "(1, 2, object())" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_signed_literal_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(LiteralPattern("-3.5"), "branch_0"),
            GeneratedCase(LiteralPattern("+1"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "value == -3.5" in source
    assert "value == +1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_signed_nested_literal_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        ("x", LiteralPattern("+1")),
                        (
                            "y",
                            SequencePattern(
                                (LiteralPattern("-3.5"), LiteralPattern("-1")),
                                bracketed=True,
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "value.x == +1" in source
    assert "value.y[0] == -3.5" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_guarded_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(
                    OrPattern((LiteralPattern("1"), SingletonPattern("None"))),
                    "not False",
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_false_guarded_generated_program_falls_through(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(GuardedPattern(LiteralPattern("1"), "False"), "branch_0"),
            GeneratedCase(LiteralPattern("1"), "branch_1"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_computed_guarded_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(LiteralPattern("1"), "len([None]) == 1"),
                "branch_0",
            ),
            GeneratedCase(LiteralPattern("2"), "branch_1"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_subject_guarded_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(LiteralPattern("1"), "{subject} is not None"),
                "branch_0",
            ),
            GeneratedCase(LiteralPattern("2"), "branch_1"),
        ),
    )

    source = program.to_trace_if_code()
    assert "value is not None" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_guarded_sequence_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                GuardedPattern(
                    GappedSequencePattern((LiteralPattern("1"), None), False),
                    "not False",
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_guarded_attribute_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        (
                            "x",
                            GuardedPattern(
                                LiteralPattern("1"),
                                "not isinstance({subject}, dict)",
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "not isinstance(value.x, dict)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_guarded_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (
                        GuardedPattern(
                            LiteralPattern("1"),
                            "hasattr({subject}, '__class__')",
                        ),
                    ),
                    False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "hasattr(value[0], '__class__')" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_or_attribute_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        (
                            "x",
                            OrPattern((LiteralPattern("1"), LiteralPattern("2"))),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "(value.x == 1 or value.x == 2)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_or_sequence_element_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (OrPattern((LiteralPattern("1"), LiteralPattern("2"))),),
                    False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "(value[0] == 1 or value[0] == 2)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_class_or_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (OrPattern((ClassPattern("Point"), ClassPattern("Token"))),),
                    False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], Point) or isinstance(value[0], Token)" in source
    assert "Point()" in source
    assert "Token()" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_class_attribute_or_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (
                        OrPattern(
                            (
                                ClassPattern("Point", (("kind", LiteralPattern("1")),)),
                                ClassPattern("Token", (("kind", LiteralPattern("2")),)),
                            )
                        ),
                    ),
                    False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], Point)" in source
    assert "value[0].kind == 1" in source
    assert "isinstance(value[0], Token)" in source
    assert "value[0].kind == 2" in source
    assert "Point(kind=1)" in source
    assert "Token(kind=2)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_class_union_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (
                        ClassUnionPattern(
                            ("Point", "Token"),
                            (("kind", LiteralPattern("1")),),
                        ),
                    ),
                    False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], (Point, Token))" in source
    assert "value[0].kind == 1" in source
    assert "[Point(kind=1)]" in source
    assert "[Token(kind=1)]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_nested_class_union_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    pattern = SequencePattern(
        (
            ClassUnionPattern(
                ("Point", "Token"),
                (("node", ClassPattern("Node", (("kind", LiteralPattern("1")),))),),
            ),
        ),
        bracketed=False,
    )
    program = GeneratedProgram(
        classes=("Point", "Token", "Node"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_recursive_nested_class_union_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    pattern = SequencePattern(
        (
            generate_sequence_element_nested_class_union_pattern(
                random.Random(0), ("Point", "Token", "Node"), depth=3
            ),
        ),
        bracketed=False,
    )
    program = GeneratedProgram(
        classes=("Point", "Token", "Node"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], (Token, Point, Node))" in source
    assert "isinstance(value[0].kind.y, (list, tuple))" in source
    assert "value[0].kind.y[0][0].kind.x is True" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_class_or_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern("Point"),
                        ClassPattern("Token"),
                        LiteralPattern("1"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value, Point) or isinstance(value, Token)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_class_attribute_or_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern("Point", (("kind", LiteralPattern("1")),)),
                        ClassPattern("Token"),
                        SingletonPattern("None"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(LiteralPattern("2"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value, Point)" in source
    assert "value.kind == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_class_sequence_attribute_or_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern(
                            "Point",
                            (
                                (
                                    "items",
                                    SequencePattern(
                                        (
                                            LiteralPattern("1"),
                                            SingletonPattern("None"),
                                        ),
                                        bracketed=True,
                                    ),
                                ),
                            ),
                        ),
                        ClassPattern("Token"),
                        LiteralPattern("0"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("False"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.items, (list, tuple))" in source
    assert "value.items[0] == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_sequence_or_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Token",),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        SequencePattern(
                            (LiteralPattern("1"), LiteralPattern("2")),
                            bracketed=False,
                        ),
                        ClassPattern("Token"),
                        SingletonPattern("None"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(LiteralPattern("3"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "len(value) == 2" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_or_with_class_attribute_or_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        SequencePattern(
                            (
                                OrPattern(
                                    (
                                        ClassPattern(
                                            "Point", (("kind", LiteralPattern("1")),)
                                        ),
                                        ClassPattern(
                                            "Token", (("kind", LiteralPattern("2")),)
                                        ),
                                    )
                                ),
                            ),
                            bracketed=False,
                        ),
                        LiteralPattern("'ready'"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], Point)" in source
    assert "isinstance(value[0], Token)" in source
    assert "value == 'ready'" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_sequence_or_with_nested_class_attribute_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token", "Node"),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (
                        OrPattern(
                            (
                                ClassPattern(
                                    "Point",
                                    (
                                        (
                                            "node",
                                            ClassPattern(
                                                "Node",
                                                (("kind", LiteralPattern("1")),),
                                            ),
                                        ),
                                    ),
                                ),
                                ClassPattern("Token"),
                            )
                        ),
                    ),
                    bracketed=False,
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert (
        'hasattr(value[0], "node")' in source or "hasattr(value[0], 'node')" in source
    )
    assert "isinstance(value[0].node, Node)" in source
    assert (
        'hasattr(value[0].node, "kind")' in source
        or "hasattr(value[0].node, 'kind')" in source
    )
    assert "value[0].node.kind == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_sequence_or_nested_class_attribute_program_survives_matchify(
    tmp_path: Path,
):
    pattern = SequencePattern(
        (
            generate_or_nested_class_attribute_pattern(
                random.Random(0), ("Point", "Token", "Node")
            ),
        ),
        bracketed=False,
    )
    program = GeneratedProgram(
        classes=("Point", "Token", "Node"),
        cases=(
            GeneratedCase(pattern, "branch_0"),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_or_with_class_union_sequence_element_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        SequencePattern(
                            (
                                ClassUnionPattern(
                                    ("Point", "Token"),
                                    (("kind", LiteralPattern("1")),),
                                ),
                            ),
                            bracketed=False,
                        ),
                        LiteralPattern("'ready'"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value[0], (Point, Token))" in source
    assert "value[0].kind == 1" in source
    assert "value == 'ready'" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_recursive_sequence_or_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Token"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        SequencePattern(
                            (
                                ClassPattern(
                                    "Point",
                                    (
                                        (
                                            "items",
                                            SequencePattern(
                                                (
                                                    LiteralPattern("1"),
                                                    SingletonPattern("None"),
                                                ),
                                                bracketed=True,
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                            bracketed=False,
                        ),
                        ClassPattern("Token", (("kind", LiteralPattern("'ready'")),)),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(LiteralPattern("3"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "value[0].items[0] == 1" in source
    assert "value.kind == 'ready'" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_nested_class_or_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Node"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern(
                            "Point",
                            (
                                (
                                    "x",
                                    ClassPattern(
                                        "Node", (("kind", LiteralPattern("1")),)
                                    ),
                                ),
                            ),
                        ),
                        LiteralPattern("0"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.x, Node)" in source
    assert "value.x.kind == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_deep_nested_class_or_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Node", "Leaf"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern(
                            "Point",
                            (
                                (
                                    "x",
                                    ClassPattern(
                                        "Node",
                                        (
                                            (
                                                "y",
                                                ClassPattern(
                                                    "Leaf",
                                                    (
                                                        (
                                                            "kind",
                                                            LiteralPattern("1"),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                        LiteralPattern("0"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.x.y, Leaf)" in source
    assert "value.x.y.kind == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_four_level_nested_class_or_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Root", "Point", "Node", "Leaf"),
        cases=(
            GeneratedCase(
                OrPattern(
                    (
                        ClassPattern(
                            "Root",
                            (
                                (
                                    "child",
                                    ClassPattern(
                                        "Point",
                                        (
                                            (
                                                "child",
                                                ClassPattern(
                                                    "Node",
                                                    (
                                                        (
                                                            "child",
                                                            ClassPattern(
                                                                "Leaf",
                                                                (
                                                                    (
                                                                        "kind",
                                                                        LiteralPattern(
                                                                            "1"
                                                                        ),
                                                                    ),
                                                                ),
                                                            ),
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                        LiteralPattern("0"),
                    )
                ),
                "branch_0",
            ),
            GeneratedCase(SingletonPattern("None"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "isinstance(value.child.child.child, Leaf)" in source
    assert "value.child.child.child.kind == 1" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_attribute_guarded_class_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                AttributeGuardedClassPattern("Point", "x", "len([None])", "1"),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
        ),
    )

    assert_matchify_preserves_trace(program, tmp_path)


def test_relational_guarded_class_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                RelationalGuardedClassPattern("Point", "x", ">", "0", "1", "0"),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(x=1)" in source
    assert "Point(x=0)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_not_equal_guarded_class_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                RelationalGuardedClassPattern("Point", "x", "!=", "0", "1", "0"),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(x=1)" in source
    assert "Point(x=0)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_less_equal_guarded_class_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                RelationalGuardedClassPattern("Point", "x", "<=", "1", "1", "2"),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(x=1)" in source
    assert "Point(x=2)" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_nested_attribute_guarded_generated_program_survives_matchify(tmp_path: Path):
    program = GeneratedProgram(
        classes=("Point", "Node"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        (
                            "child",
                            AttributeGuardedClassPattern(
                                "Node", "x", "len([None])", "1"
                            ),
                        ),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "Point(child=Node(x=1))" in source
    assert "Point(child=Node(x=0))" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_sequence_element_attribute_guarded_generated_program_survives_matchify(
    tmp_path: Path,
):
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(
                SequencePattern(
                    (AttributeGuardedClassPattern("Point", "x", "len([None])", "1"),),
                    bracketed=False,
                ),
                "branch_0",
            ),
            GeneratedCase(ClassPattern("Point"), "branch_1"),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    source = program.to_trace_if_code()
    assert "[Point(x=1)]" in source
    assert "[Point(x=0)]" in source
    assert_matchify_preserves_trace(program, tmp_path)


def test_generated_if_traces_survive_matchify(tmp_path: Path):
    converted = 0
    for program in generated_programs(count=80, seed=20260625):
        converted += int(
            assert_matchify_preserves_trace(program, tmp_path, require_changed=False)
        )
    assert converted > 0
