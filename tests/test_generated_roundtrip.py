import random
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO

from inline_snapshot import snapshot

from matchify.transform import transform_code


@dataclass(frozen=True)
class LiteralPattern:
    value: str

    def to_code(self) -> str:
        return self.value

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return f"{subject} == {self.value}"

    def to_value_code(self) -> str:
        return self.value


@dataclass(frozen=True)
class SingletonPattern:
    value: str

    def to_code(self) -> str:
        return self.value

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return f"{subject} is {self.value}"

    def to_value_code(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrPattern:
    alternatives: tuple["GeneratedPattern", ...]

    def to_code(self) -> str:
        return " | ".join(pattern.to_code() for pattern in self.alternatives)

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return " or ".join(
            pattern.to_condition_code(subject, safe=safe)
            for pattern in self.alternatives
        )

    def to_value_code(self) -> str:
        return self.alternatives[0].to_value_code()


@dataclass(frozen=True)
class ClassPattern:
    class_name: str
    attrs: tuple[tuple[str, "GeneratedPattern"], ...] = ()

    def to_code(self) -> str:
        if not self.attrs:
            return f"{self.class_name}()"
        attrs = tuple(sorted(self.attrs, key=class_attr_sort_key))
        attr_code = ", ".join(f"{attr}={pattern.to_code()}" for attr, pattern in attrs)
        return f"{self.class_name}({attr_code})"

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
class SequencePattern:
    elements: tuple["GeneratedPattern", ...]
    bracketed: bool

    def to_code(self) -> str:
        elements = ", ".join(element.to_code() for element in self.elements)
        if self.bracketed:
            return f"[{elements}]"
        if len(self.elements) == 1:
            return f"{elements},"
        return elements

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
class WildcardPattern:
    def to_code(self) -> str:
        return "_"

    def to_condition_code(self, subject: str, safe: bool = False) -> str:
        return "True"

    def to_value_code(self) -> str:
        return "object()"


GeneratedPattern = (
    LiteralPattern
    | SingletonPattern
    | OrPattern
    | ClassPattern
    | SequencePattern
    | WildcardPattern
)


def class_attr_sort_key(attr_pattern: tuple[str, GeneratedPattern]) -> tuple[int, str]:
    attr, pattern = attr_pattern
    return (0 if isinstance(pattern, SequencePattern) else 1, attr)


@dataclass(frozen=True)
class GeneratedCase:
    pattern: GeneratedPattern
    body: str


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

    def to_match_code(self, value_code: str = "None") -> str:
        class_defs = self.class_defs_code()
        case_blocks = "\n".join(
            f"    case {case.pattern.to_code()}:\n        result = {case.body!r}"
            for case in self.cases
        )
        return (
            f"{class_defs}result = 'unmatched'\n"
            f"value = {value_code}\nmatch value:\n{case_blocks}\n"
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

    def sample_value_codes(self) -> list[str]:
        values = [
            case.pattern.to_value_code()
            for case in self.cases
            if not isinstance(case.pattern, WildcardPattern)
        ]
        values.append("object()")
        return values


def generated_programs(count: int, seed: int) -> list[GeneratedProgram]:
    rng = random.Random(seed)
    return [generate_program(rng) for _ in range(count)]


def generate_program(rng: random.Random) -> GeneratedProgram:
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


def generate_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    choices = ["literal", "singleton", "or_literal", "class", "sequence"]
    if depth > 0:
        choices.extend(["nested_class", "nested_sequence"])
    kind = rng.choice(choices)

    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        values = rng.sample(["0", "1", "2", "'red'", "'blue'", "None", "False"], 3)
        return OrPattern(
            tuple(pattern_from_literal_or_singleton(value) for value in values)
        )
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=0)
    if kind == "nested_class":
        return generate_class_pattern(rng, classes, depth=depth)
    if kind == "nested_sequence":
        return generate_sequence_pattern(
            rng, classes, depth=depth, bracketed=False, allow_nested_sequence=True
        )

    return generate_sequence_pattern(
        rng, classes, depth=0, bracketed=False, allow_nested_sequence=False
    )


def generate_class_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> ClassPattern:
    class_name = rng.choice(classes)
    attrs = rng.sample(["x", "y", "kind"], rng.randint(0, 2))
    attr_patterns = tuple(
        (attr, generate_attribute_pattern(rng, classes, depth)) for attr in attrs
    )
    return ClassPattern(class_name, attr_patterns)


def generate_attribute_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    if depth <= 0:
        return generate_literal_or_singleton(rng)
    choices = ["literal", "singleton", "class", "sequence"]
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=0)
    return generate_sequence_pattern(
        rng, classes, depth - 1, bracketed=True, allow_nested_sequence=False
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


def generate_sequence_element_pattern(
    rng: random.Random,
    classes: tuple[str, ...],
    depth: int,
    allow_nested_sequence: bool,
) -> GeneratedPattern:
    """Generate only sequence elements Matchify can currently reconstruct."""
    if depth <= 0:
        return generate_literal_or_singleton(rng)

    choices = ["literal", "singleton", "class"]
    if allow_nested_sequence:
        choices.append("sequence")
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=0)
    return generate_sequence_pattern(
        rng,
        classes,
        0,
        bracketed=True,
        allow_nested_sequence=False,
    )


def pattern_from_literal_or_singleton(value: str) -> LiteralPattern | SingletonPattern:
    if value in {"None", "True", "False"}:
        return SingletonPattern(value)
    return LiteralPattern(value)


def generate_literal_or_singleton(
    rng: random.Random,
) -> LiteralPattern | SingletonPattern:
    if rng.choice([True, False]):
        return LiteralPattern(generate_literal(rng))
    return SingletonPattern(rng.choice(["None", "True", "False"]))


def generate_literal(rng: random.Random) -> str:
    return rng.choice(["-1", "0", "1", "2", "3.5", "'red'", "'blue'", "'ready'"])


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


def assert_round_trips(program: GeneratedProgram) -> None:
    if_else_code = program.to_if_code()
    match_code = program.to_match_code()
    transformed = transform_code(if_else_code)
    assert transformed.strip() == match_code.strip(), (
        f"Round-trip mismatch\nGenerated match:\n{match_code}\n"
        f"Generated if/else:\n{if_else_code}\nRematchified:\n{transformed}"
    )


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
        program.to_match_code().rstrip()
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
result = 'unmatched'
value = None
match value:
    case Point(kind='ready'):
        result = 'branch_0'
    case False:
        result = 'branch_1'
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
result = 'unmatched'
value = None
match value:
    case [1],:
        result = 'branch_0'
    case Point(x=1):
        result = 'branch_1'
    case -1:
        result = 'branch_2'
    case False:
        result = 'branch_3'
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
result = 'unmatched'
value = None
match value:
    case None, None:
        result = 'branch_0'
    case Point():
        result = 'branch_1'
    case _:
        result = 'default'
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
result = 'unmatched'
value = None
match value:
    case True,:
        result = 'branch_0'
    case Point(x=['blue', False]):
        result = 'branch_1'
    case 'ready':
        result = 'branch_2'
    case [-1], [False, True]:
        result = 'branch_3'
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
result = 'unmatched'
value = None
match value:
    case Point(y=[Point(x='red', y=3.5)], x=1):
        result = 'branch_0'
    case [-1, None], Point(kind=2, x=False), None:
        result = 'branch_1'
    case None | 2 | 0:
        result = 'branch_2'
    case _:
        result = 'default'\
"""
    )


def test_generated_match_patterns_round_trip_through_matchify():
    for program in generated_programs(count=80, seed=20260623):
        assert_round_trips(program)


def test_generated_if_and_match_programs_execute_the_same():
    for program in generated_programs(count=80, seed=20260623):
        for value_code in program.sample_value_codes():
            assert execute_result(
                program.to_if_code(value_code, safe=True)
            ) == execute_result(program.to_match_code(value_code))
