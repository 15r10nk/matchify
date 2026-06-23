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
            branch_blocks.append(
                f"    {keyword} {condition}:\n        print({case.body!r})"
            )
        branches = "\n".join(branch_blocks)
        return f"{class_defs}values = [\n{value_lines}\n]\nfor value in values:\n{branches}\n"

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
        return generate_or_literal_pattern(rng)
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


def generate_attribute_pattern(
    rng: random.Random, classes: tuple[str, ...], depth: int
) -> GeneratedPattern:
    if depth <= 0:
        return generate_literal_or_singleton(rng)
    choices = ["literal", "singleton", "or_literal", "class", "sequence"]
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=depth - 1)
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


def generate_sequence_element_pattern(
    rng: random.Random,
    classes: tuple[str, ...],
    depth: int,
    allow_nested_sequence: bool,
) -> GeneratedPattern:
    """Generate only sequence elements Matchify can currently reconstruct."""
    if depth <= 0:
        return generate_literal_or_singleton(rng)

    choices = ["literal", "singleton", "or_literal", "class"]
    if allow_nested_sequence:
        choices.append("sequence")
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(generate_literal(rng))
    if kind == "singleton":
        return SingletonPattern(rng.choice(["None", "True", "False"]))
    if kind == "or_literal":
        return generate_or_literal_pattern(rng)
    if kind == "class":
        return generate_class_pattern(rng, classes, depth=depth - 1)
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
    Point(kind='ready'),
    [Point(kind=True, x=True)],
    object(),
]
for value in values:
    if isinstance(value, (Point, Token)) and hasattr(value, 'kind') and value.kind == 'ready':
        print('branch_0')
    elif isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], (Point, Token)) and hasattr(value[0], 'kind') and value[0].kind is True and hasattr(value[0], 'x') and value[0].x is True:
        print('branch_1')
    else:
        print('default')
---
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    0,
    [None, None, False],
    0,
    ['red'],
    object(),
]
for value in values:
    if (value == 0 or value == 'blue' or value == 'red'):
        print('branch_0')
    elif isinstance(value, (list, tuple)) and len(value) == 3 and value[0] is None and value[1] is None and value[2] is False:
        print('branch_1')
    elif value == 0:
        print('branch_2')
    elif isinstance(value, (list, tuple)) and len(value) == 1 and value[0] == 'red':
        print('branch_3')
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
    Point(x=Token()),
    Point(kind=1, y=Point(kind=1, x=Point(kind=None, y=False))),
    [[None]],
    [Token(kind=0, x=Token(kind='ready', y=0)), None, 0],
    [2, None],
    object(),
]
for value in values:
    if isinstance(value, Point) and hasattr(value, 'x') and isinstance(value.x, Token):
        print('branch_0')
    elif isinstance(value, Point) and hasattr(value, 'kind') and value.kind == 1 and hasattr(value, 'y') and isinstance(value.y, Point) and hasattr(value.y, 'kind') and value.y.kind == 1 and hasattr(value.y, 'x') and isinstance(value.y.x, (Point, Token)) and hasattr(value.y.x, 'kind') and value.y.x.kind is None and hasattr(value.y.x, 'y') and value.y.x.y is False:
        print('branch_1')
    elif isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], (list, tuple)) and len(value[0]) == 1 and (value[0][0] is None or value[0][0] == 1 or value[0][0] == 2):
        print('branch_2')
    elif isinstance(value, (list, tuple)) and len(value) == 3 and isinstance(value[0], (Token, Point)) and hasattr(value[0], 'kind') and value[0].kind == 0 and hasattr(value[0], 'x') and isinstance(value[0].x, (Token, Point)) and hasattr(value[0].x, 'kind') and value[0].x.kind == 'ready' and hasattr(value[0].x, 'y') and value[0].x.y == 0 and value[1] is None and value[2] == 0:
        print('branch_3')
    elif isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 2 and value[1] is None:
        print('branch_4')
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
    Node(),
    None,
    object(),
]
for value in values:
    if isinstance(value, (Node, Token)):
        print('branch_0')
    elif value is None:
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

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)
values = [
    None,
    Point(),
    object(),
]
for value in values:
    if value is None:
        print('branch_0')
    elif isinstance(value, (Point, Node)):
        print('branch_1')\
"""
    )


def test_generated_if_traces_survive_matchify(tmp_path: Path):
    for program in generated_programs(count=80, seed=20260625):
        assert_matchify_preserves_trace(program, tmp_path)
