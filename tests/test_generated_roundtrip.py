import random
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from inline_snapshot import snapshot

from matchify.cli import convert_file


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
    """Generates `subject == a or subject == b`, matching `case a | b:`."""

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
        return f"{self.pattern.to_condition_code(subject, safe=safe)} and {self.guard}"

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
class SequencePattern:
    """Generates `len(subject) == n and subject[i] ...`, matching sequence cases."""

    elements: tuple["GeneratedPattern", ...]
    bracketed: bool

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
        return f"[{elements}]"


@dataclass(frozen=True)
class GappedSequencePattern:
    """Generates `len(subject) == n` with skipped indices, matching `_` gaps."""

    elements: tuple["GeneratedPattern | None", ...]
    bracketed: bool

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
        return f"[{elements}]"


@dataclass(frozen=True)
class StarSequencePattern:
    """Generates `len(subject) >= n and subject[i] ...`, matching `case [..., *_]:`."""

    elements: tuple["GeneratedPattern", ...]

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
        return f"[{elements}]"


@dataclass(frozen=True)
class GappedStarSequencePattern:
    """Generates `len(subject) >= n` with skipped prefix indices before `*_`."""

    elements: tuple["GeneratedPattern | None", ...]

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
        return f"[{elements}]"


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


def contains_capture(pattern: GeneratedPattern) -> bool:
    if isinstance(pattern, CaptureClassPattern):
        return True
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
            values.append(case.pattern.to_value_code())
            fallthrough_value = fallthrough_value_code(case.pattern)
            if fallthrough_value is not None:
                values.append(fallthrough_value)
        values.append("object()")
        return values


def fallthrough_value_code(pattern: GeneratedPattern) -> str | None:
    if isinstance(pattern, AttributeGuardedClassPattern):
        return (
            f"{pattern.class_name}({pattern.attr}={mismatching_literal(pattern.value)})"
        )
    if isinstance(pattern, RelationalGuardedClassPattern):
        return f"{pattern.class_name}({pattern.attr}={pattern.fallthrough_value})"
    if isinstance(pattern, CaptureClassPattern):
        elements = ", ".join(
            "object()" for _ in range(max(pattern.required_length() - 1, 0))
        )
        return f"{pattern.class_name}({pattern.attr}=[{elements}])"
    if isinstance(pattern, GuardedPattern):
        return fallthrough_value_code(pattern.pattern)
    if isinstance(pattern, ClassPattern):
        return class_fallthrough_value_code(pattern.class_name, pattern.attrs)
    if isinstance(pattern, ClassUnionPattern):
        return class_fallthrough_value_code(pattern.class_names[0], pattern.attrs)
    if isinstance(pattern, SequencePattern):
        return sequence_fallthrough_value_code(pattern.elements)
    if isinstance(pattern, GappedSequencePattern):
        return sequence_fallthrough_value_code(pattern.elements)
    if isinstance(pattern, StarSequencePattern):
        return sequence_fallthrough_value_code(pattern.elements, append_extra=True)
    if isinstance(pattern, GappedStarSequencePattern):
        return sequence_fallthrough_value_code(pattern.elements, append_extra=True)
    return None


def class_fallthrough_value_code(
    class_name: str, attrs: tuple[tuple[str, GeneratedPattern], ...]
) -> str | None:
    attr_values = []
    found_fallthrough = False
    for attr, pattern in sorted(attrs, key=class_attr_sort_key):
        value = None if found_fallthrough else fallthrough_value_code(pattern)
        if value is None:
            value = pattern.to_value_code()
        else:
            found_fallthrough = True
        attr_values.append(f"{attr}={value}")

    if not found_fallthrough:
        return None

    return f"{class_name}({', '.join(attr_values)})"


def sequence_fallthrough_value_code(
    elements: tuple[GeneratedPattern | None, ...], append_extra: bool = False
) -> str | None:
    element_values = []
    found_fallthrough = False
    for element in elements:
        if element is None:
            element_values.append("object()")
            continue

        value = None if found_fallthrough else fallthrough_value_code(element)
        if value is None:
            value = element.to_value_code()
        else:
            found_fallthrough = True
        element_values.append(value)

    if append_extra:
        element_values.append("object()")

    if not found_fallthrough:
        return None

    return f"[{', '.join(element_values)}]"


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
        GeneratedCase(generate_pattern(rng, classes, depth=2), f"branch_{index}")
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
    return isinstance(pattern, GuardedPattern) and pattern.guard == "False"


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
        "guarded",
        "sequence",
        "gapped_sequence",
        "star",
        "gapped_star",
    ]
    if depth > 0:
        choices.extend(["nested_class", "nested_sequence"])
    kind = rng.choice(choices)

    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=0)
    if kind == "attribute_guarded_class":
        return generate_attribute_guarded_class_pattern(rng, classes)
    if kind == "relational_guarded_class":
        return generate_relational_guarded_class_pattern(rng, classes)
    if kind == "capture_class":
        return generate_capture_class_pattern(rng, classes)
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
    length = rng.randint(1, 3)
    capture_indices = tuple(
        index for index in range(length) if rng.choice([True, False])
    )
    if not capture_indices:
        capture_indices = (rng.randrange(length),)
    return CaptureClassPattern(class_name, attr, capture_indices)


def generate_guarded_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GuardedPattern:
    kind = rng.choice(
        [
            "literal",
            "singleton",
            "or_literal",
            "class",
            "attribute_guarded_class",
            "relational_guarded_class",
            "capture_class",
            "sequence",
            "gapped_sequence",
            "star",
            "gapped_star",
        ]
    )
    if kind == "literal":
        pattern: GeneratedPattern = LiteralPattern(generate_literal(rng))
    elif kind == "singleton":
        pattern = SingletonPattern(rng.choice(["None", "True", "False"]))
    elif kind == "or_literal":
        pattern = generate_or_literal_pattern(rng)
    elif kind == "class":
        pattern = generate_class_pattern(rng, classes, depth=depth)
    elif kind == "attribute_guarded_class":
        pattern = generate_attribute_guarded_class_pattern(rng, classes)
    elif kind == "relational_guarded_class":
        pattern = generate_relational_guarded_class_pattern(rng, classes)
    elif kind == "capture_class":
        pattern = generate_capture_class_pattern(rng, classes)
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
            "False",
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
        "sequence",
        "gapped_sequence",
        "star",
        "gapped_star",
    ]
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=depth - 1)
    if kind == "attribute_guarded_class":
        return generate_attribute_guarded_class_pattern(rng, classes)
    if kind == "relational_guarded_class":
        return generate_relational_guarded_class_pattern(rng, classes)
    if kind == "capture_class":
        return generate_capture_class_pattern(rng, classes)
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
    return SequencePattern(elements, bracketed=bracketed)


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
    return GappedSequencePattern(elements, bracketed=bracketed)


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
    return StarSequencePattern(elements)


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
    return GappedStarSequencePattern(elements)


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
    ]
    if allow_nested_sequence:
        choices.extend(["sequence", "gapped_sequence", "star", "gapped_star"])
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=depth - 1)
    if kind == "attribute_guarded_class":
        return generate_attribute_guarded_class_pattern(rng, classes)
    if kind == "relational_guarded_class":
        return generate_relational_guarded_class_pattern(rng, classes)
    if kind == "capture_class":
        return generate_capture_class_pattern(rng, classes)
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


def generate_or_literal_pattern(rng: random.Random) -> OrPattern:
    values = rng.sample(["0", "1", "2", "'red'", "'blue'", "None", "False"], 3)
    return OrPattern(
        tuple(pattern_from_literal_or_singleton(value) for value in values)
    )


def generate_literal_or_singleton(
    rng: random.Random,
) -> LiteralPattern | SingletonPattern:
    if rng.choice([True, False]):
        return LiteralPattern(generate_literal(rng))
    return SingletonPattern(rng.choice(["None", "True", "False"]))


def generate_literal(rng: random.Random) -> str:
    return rng.choice(["-1", "0", "1", "2", "3.5", "'red'", "'blue'", "'ready'"])


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


def assert_matchify_preserves_trace(program: GeneratedProgram, tmp_path: Path) -> None:
    if_else_code = program.to_trace_if_code()
    path = tmp_path / "generated.py"
    path.write_text(if_else_code, encoding="utf-8")
    expected_trace = execute_result(if_else_code)

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert changed is True
    assert error is None
    transformed = path.read_text(encoding="utf-8")
    assert " match " in transformed

    assert execute_result(transformed) == expected_trace, (
        f"Trace mismatch\nGenerated if/else:\n{if_else_code}\n"
        f"Matchified code:\n{transformed}"
    )


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


def test_pattern_ir_generates_if_conditions():
    pattern = ClassPattern(
        "Point",
        (
            ("x", LiteralPattern("1")),
            (
                "y",
                SequencePattern(
                    (
                        ClassPattern(
                            "Node",
                            (
                                ("kind", SingletonPattern("None")),
                                ("x", LiteralPattern("'ready'")),
                            ),
                        ),
                        SequencePattern(
                            (LiteralPattern("2"), SingletonPattern("False")),
                            bracketed=True,
                        ),
                    ),
                    bracketed=True,
                ),
            ),
        ),
    )

    assert pattern.to_condition_code("value") == snapshot(
        "isinstance(value, Point) and len(value.y) == 2 and isinstance(value.y[0], Node) and value.y[0].kind is None and value.y[0].x == 'ready' and len(value.y[1]) == 2 and value.y[1][0] == 2 and value.y[1][1] is False and value.x == 1"
    )


def test_pattern_ir_generates_matching_values():
    pattern = SequencePattern(
        (
            OrPattern((LiteralPattern("'red'"), LiteralPattern("'blue'"))),
            ClassPattern("Point", (("x", SingletonPattern("True")),)),
            SequencePattern((LiteralPattern("1"), SingletonPattern("None")), True),
        ),
        bracketed=False,
    )

    assert pattern.to_value_code() == snapshot("['red', Point(x=True), [1, None]]")


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


def test_sample_values_must_cover_reachable_generated_cases():
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(ClassPattern("Point"), "branch_0"),
            GeneratedCase(
                ClassPattern("Point", (("x", LiteralPattern("1")),)), "branch_1"
            ),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    assert not sample_values_cover_reachable_cases(program)


def test_false_guarded_generated_cases_are_not_required_for_sample_coverage():
    program = GeneratedProgram(
        classes=("Point",),
        cases=(
            GeneratedCase(GuardedPattern(LiteralPattern("1"), "False"), "branch_0"),
            GeneratedCase(LiteralPattern("1"), "branch_1"),
        ),
    )

    assert sample_values_cover_reachable_cases(program)


def test_generated_program_if_code_is_stable():
    program = GeneratedProgram(
        classes=("Point", "Node"),
        cases=(
            GeneratedCase(
                ClassPattern(
                    "Point",
                    (
                        ("x", LiteralPattern("1")),
                        ("y", ClassPattern("Node", (("kind", LiteralPattern("'n'")),))),
                    ),
                ),
                "branch_0",
            ),
            GeneratedCase(
                SequencePattern((LiteralPattern("1"), SingletonPattern("None")), False),
                "branch_1",
            ),
            GeneratedCase(WildcardPattern(), "default"),
        ),
    )

    assert program.to_if_code("Point(x=1, y=Node(kind='n'))") == snapshot(
        """\
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
result = 'unmatched'
value = Point(x=1, y=Node(kind='n'))
if isinstance(value, Point) and value.x == 1 and isinstance(value.y, Node) and value.y.kind == 'n':
    result = 'branch_0'
elif len(value) == 2 and value[0] == 1 and value[1] is None:
    result = 'branch_1'
else:
    result = 'default'
"""
    )


def test_generate_program_samples_are_stable():
    samples = "\n---\n".join(
        program.to_trace_if_code().rstrip()
        for program in generated_programs(count=5, seed=20260623)
    )

    assert samples == snapshot(
        """\
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    Point(y=[1, 2, 3, object()]),
    Point(y=[object(), object()]),
    [None, None, None],
    object(),
]
for value in values:
    if isinstance(value, Point) and hasattr(value, 'y') and isinstance(value.y, (list, tuple)) and len(value.y) >= 3:
        capture_0_0 = value.y[0]
        capture_0_1 = value.y[2]
        print('branch_0')
    elif isinstance(value, (list, tuple)) and len(value) == 3 and value[0] is None and value[1] is None and value[2] is None:
        print('branch_1')
    else:
        print('default')
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    [Token(items=[1, object()])],
    [Token(items=[])],
    Point(items=[1, object()]),
    Point(items=[]),
    object(),
]
for value in values:
    if isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], Token) and hasattr(value[0], 'items') and isinstance(value[0].items, (list, tuple)) and len(value[0].items) >= 1 and (1 < 2 and 'x'.islower()):
        capture_0_0 = value[0].items[0]
        print('branch_0')
    elif isinstance(value, Point) and hasattr(value, 'items') and isinstance(value.items, (list, tuple)) and len(value.items) >= 1:
        capture_1_0 = value.items[0]
        print('branch_1')
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    [object(), object(), [object(), Point(items=[1, object()]), [object(), False], object()], [['ready', object()], False], object()],
    [object(), object(), [object(), Point(items=[]), [object(), False], object()], [['ready', object()], False], object()],
    Token(kind=1),
    Token(kind=0),
    Point(kind=[[0, object(), object()], True, [2, 0]], x=[Point(y=1), 1, object(), None]),
    Point(kind=[[0, object(), object()], True, [2, 0]], x=[Point(y=2), 1, object(), None]),
    Token(x=1),
    2,
    object(),
]
for value in values:
    if isinstance(value, (list, tuple)) and len(value) == 5 and isinstance(value[2], (list, tuple)) and len(value[2]) >= 3 and isinstance(value[2][1], Point) and hasattr(value[2][1], 'items') and isinstance(value[2][1].items, (list, tuple)) and len(value[2][1].items) >= 1 and isinstance(value[2][2], (list, tuple)) and len(value[2][2]) == 2 and value[2][2][1] is False and isinstance(value[3], (list, tuple)) and len(value[3]) == 2 and isinstance(value[3][0], (list, tuple)) and len(value[3][0]) >= 1 and value[3][0][0] == 'ready' and value[3][1] is False:
        capture_0_0 = value[2][1].items[0]
        print('branch_0')
    elif isinstance(value, Token) and hasattr(value, 'kind') and value.kind > 0:
        print('branch_1')
    elif isinstance(value, (Point, Token)) and hasattr(value, 'kind') and isinstance(value.kind, (list, tuple)) and len(value.kind) == 3 and isinstance(value.kind[0], (list, tuple)) and len(value.kind[0]) == 3 and value.kind[0][0] == 0 and value.kind[1] is True and isinstance(value.kind[2], (list, tuple)) and len(value.kind[2]) == 2 and value.kind[2][0] == 2 and value.kind[2][1] == 0 and hasattr(value, 'x') and isinstance(value.x, (list, tuple)) and len(value.x) == 4 and isinstance(value.x[0], Point) and hasattr(value.x[0], 'y') and value.x[0].y < 2 and value.x[1] == 1 and (value.x[3] is None or value.x[3] == 'red' or value.x[3] == 1):
        print('branch_2')
    elif isinstance(value, (Token, Point)) and hasattr(value, 'x') and (value.x == 1 or value.x == 0 or value.x is False):
        print('branch_3')
    elif (value == 2 or value == 1 or value == 'blue'):
        print('branch_4')
    else:
        print('default')
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    Token(x=[1, object()]),
    Token(x=[]),
    Token(),
    object(),
]
for value in values:
    if isinstance(value, Token) and hasattr(value, 'x') and isinstance(value.x, (list, tuple)) and len(value.x) >= 1:
        capture_0_0 = value.x[0]
        print('branch_0')
    elif isinstance(value, Token):
        print('branch_1')
    else:
        print('default')
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    Point(y='ready'),
    Point(y='miss'),
    ['blue', Point(y='ready'), [Point(kind=0, x=2), Point(y=1), [None, 'blue', 'ready']]],
    ['blue', Point(y='miss'), [Point(kind=0, x=2), Point(y=1), [None, 'blue', 'ready']]],
    object(),
]
for value in values:
    if isinstance(value, Point) and hasattr(value, 'y') and value.y == str('ready'):
        print('branch_0')
    elif isinstance(value, (list, tuple)) and len(value) == 3 and (value[0] == 'blue' or value[0] == 'red' or value[0] is False) and isinstance(value[1], Point) and hasattr(value[1], 'y') and value[1].y == str('ready') and isinstance(value[2], (list, tuple)) and len(value[2]) == 3 and isinstance(value[2][0], Point) and hasattr(value[2][0], 'kind') and value[2][0].kind == 0 and hasattr(value[2][0], 'x') and value[2][0].x == 2 and isinstance(value[2][1], Point) and hasattr(value[2][1], 'y') and value[2][1].y < 2 and isinstance(value[2][2], (list, tuple)) and len(value[2][2]) == 3 and value[2][2][0] is None and value[2][2][1] == 'blue' and value[2][2][2] == 'ready':
        print('branch_1')
    else:
        print('default')\
"""
    )


def test_generated_if_traces_survive_matchify(tmp_path: Path):
    for program in generated_programs(count=80, seed=20260625):
        assert_matchify_preserves_trace(program, tmp_path)
