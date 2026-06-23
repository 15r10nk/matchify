import random
from dataclasses import dataclass
from textwrap import dedent

import libcst as cst
from inline_snapshot import snapshot

from matchify.transform import transform_code


@dataclass(frozen=True)
class LiteralPattern:
    value: str

    def to_code(self) -> str:
        return self.value


@dataclass(frozen=True)
class SingletonPattern:
    value: str

    def to_code(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrPattern:
    alternatives: tuple["GeneratedPattern", ...]

    def to_code(self) -> str:
        return " | ".join(pattern.to_code() for pattern in self.alternatives)


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


@dataclass(frozen=True)
class WildcardPattern:
    def to_code(self) -> str:
        return "_"


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

    def to_match_code(self) -> str:
        class_defs = "\n".join(
            f"class {class_name}:\n    pass\n" for class_name in self.classes
        )
        case_blocks = "\n".join(
            f"    case {case.pattern.to_code()}:\n        result = {case.body!r}"
            for case in self.cases
        )
        return f"{class_defs}value = None\nmatch value:\n{case_blocks}\n"


def unmatchify(source: str) -> str:
    """Convert a generated match statement into an equivalent if/elif/else chain."""
    module = cst.parse_module(source)
    statements = list(module.body)
    match_index = next(
        index
        for index, statement in enumerate(statements)
        if isinstance(statement, cst.Match)
    )
    match_stmt = statements[match_index]
    assert isinstance(match_stmt, cst.Match)

    lines = [
        module.code_for_node(statement).rstrip()
        for statement in statements[:match_index]
    ]
    for index, case in enumerate(match_stmt.cases):
        body = indent_block(module.code_for_node(case.body).strip())
        if is_wildcard(case.pattern):
            lines.append(f"else:\n{body}")
            continue

        condition = condition_for_pattern(module, match_stmt.subject, case.pattern)
        keyword = "if" if index == 0 else "elif"
        lines.append(f"{keyword} {condition}:\n{body}")

    return "\n".join(lines) + "\n"


def condition_for_pattern(
    module: cst.Module, subject: cst.BaseExpression, pattern: cst.MatchPattern
) -> str:
    parts = condition_parts_for_pattern(module, subject, pattern)
    if len(parts) == 1:
        return parts[0]
    return " and ".join(parts)


def condition_parts_for_pattern(
    module: cst.Module, subject: cst.BaseExpression, pattern: cst.MatchPattern
) -> list[str]:
    if isinstance(pattern, cst.MatchValue):
        return [
            f"{module.code_for_node(subject)} == {module.code_for_node(pattern.value)}"
        ]

    if isinstance(pattern, cst.MatchSingleton):
        return [
            f"{module.code_for_node(subject)} is {module.code_for_node(pattern.value)}"
        ]

    if isinstance(pattern, cst.MatchClass):
        return condition_parts_for_class_pattern(module, subject, pattern)

    if isinstance(pattern, cst.MatchList):
        return condition_parts_for_sequence_pattern(module, subject, pattern)

    if isinstance(pattern, cst.MatchTuple):
        return condition_parts_for_sequence_pattern(module, subject, pattern)

    if isinstance(pattern, cst.MatchOr):
        return [
            " or ".join(
                condition_for_pattern(module, subject, element.pattern)
                for element in pattern.patterns
            )
        ]

    raise AssertionError(f"Unsupported generated pattern: {pattern!r}")


def condition_parts_for_class_pattern(
    module: cst.Module, subject: cst.BaseExpression, pattern: cst.MatchClass
) -> list[str]:
    subject_code = module.code_for_node(subject)
    parts = [f"isinstance({subject_code}, {module.code_for_node(pattern.cls)})"]
    for kwd in pattern.kwds:
        assert isinstance(kwd, cst.MatchKeywordElement)
        attr_subject = cst.Attribute(value=subject, attr=kwd.key)
        parts.extend(condition_parts_for_pattern(module, attr_subject, kwd.pattern))
    return parts


def condition_parts_for_sequence_pattern(
    module: cst.Module,
    subject: cst.BaseExpression,
    pattern: cst.MatchList | cst.MatchTuple,
) -> list[str]:
    elements = [element.value for element in pattern.patterns]
    subject_code = module.code_for_node(subject)
    parts = [f"len({subject_code}) == {len(elements)}"]
    for index, element in enumerate(elements):
        element_subject = cst.Subscript(
            value=subject,
            slice=[
                cst.SubscriptElement(slice=cst.Index(value=cst.Integer(str(index))))
            ],
        )
        parts.extend(condition_parts_for_pattern(module, element_subject, element))
    return parts


def is_wildcard(pattern: cst.MatchPattern) -> bool:
    return (
        isinstance(pattern, cst.MatchAs)
        and pattern.pattern is None
        and pattern.name is None
    )


def indent_block(code: str) -> str:
    return "\n".join(f"    {line}" if line else line for line in code.splitlines())


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
    max_attrs = 1 if depth > 0 else 2
    attrs = rng.sample(["x", "y", "kind"], rng.randint(0, max_attrs))
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
        # Matchify supports class checks inside sequence elements, but not
        # arbitrary scalar class attributes on those nested element patterns.
        return ClassPattern(rng.choice(classes))
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


def assert_round_trips(match_code: str) -> None:
    if_else_code = unmatchify(match_code)
    transformed = transform_code(if_else_code)
    assert cst.parse_module(transformed).deep_equals(cst.parse_module(match_code)), (
        f"Round-trip mismatch\nGenerated match:\n{match_code}\n"
        f"Unmatchified:\n{if_else_code}\nRematchified:\n{transformed}"
    )


def test_unmatchify_simple_match_statement():
    match_code = dedent(
        """
        value = None
        match value:
            case 1:
                result = 'one'
            case None:
                result = 'none'
            case _:
                result = 'default'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
value = None
if value == 1:
    result = 'one'
elif value is None:
    result = 'none'
else:
    result = 'default'
"""
    )


def test_unmatchify_or_pattern():
    match_code = dedent(
        """
        value = None
        match value:
            case 1 | 2 | None:
                result = 'small'
            case _:
                result = 'default'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
value = None
if value == 1 or value == 2 or value is None:
    result = 'small'
else:
    result = 'default'
"""
    )


def test_unmatchify_class_pattern_with_literal_attributes():
    match_code = dedent(
        """
        class Point:
            pass
        value = None
        match value:
            case Point(x=1, y=None):
                result = 'point'
            case Point():
                result = 'other point'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
class Point:
    pass
value = None
if isinstance(value, Point) and value.x == 1 and value.y is None:
    result = 'point'
elif isinstance(value, Point):
    result = 'other point'
"""
    )


def test_unmatchify_sequence_pattern():
    match_code = dedent(
        """
        value = None
        match value:
            case 1, None, 'ready':
                result = 'sequence'
            case _:
                result = 'default'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
value = None
if len(value) == 3 and value[0] == 1 and value[1] is None and value[2] == 'ready':
    result = 'sequence'
else:
    result = 'default'
"""
    )


def test_unmatchify_bracketed_sequence_pattern():
    match_code = dedent(
        """
        value = None
        match value:
            case [True, 'blue']:
                result = 'list'
            case False:
                result = 'false'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
value = None
if len(value) == 2 and value[0] is True and value[1] == 'blue':
    result = 'list'
elif value is False:
    result = 'false'
"""
    )


def test_unmatchify_nested_class_pattern():
    match_code = dedent(
        """
        class Point:
            pass
        class Node:
            pass
        value = None
        match value:
            case Point(x=Node(kind='ready')):
                result = 'nested'
            case _:
                result = 'default'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
class Point:
    pass
class Node:
    pass
value = None
if isinstance(value, Point) and isinstance(value.x, Node) and value.x.kind == 'ready':
    result = 'nested'
else:
    result = 'default'
"""
    )


def test_unmatchify_nested_sequence_pattern():
    match_code = dedent(
        """
        class Point:
            pass
        value = None
        match value:
            case [Point(x=1), [2, None]]:
                result = 'nested sequence'
            case _:
                result = 'default'
        """
    ).lstrip()

    assert unmatchify(match_code) == snapshot(
        """\
class Point:
    pass
value = None
if len(value) == 2 and isinstance(value[0], Point) and value[0].x == 1 and len(value[1]) == 2 and value[1][0] == 2 and value[1][1] is None:
    result = 'nested sequence'
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
    pass

class Token:
    pass
value = None
match value:
    case Point(kind='ready'):
        result = 'branch_0'
    case False:
        result = 'branch_1'
---
class Point:
    pass
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
    pass

class Token:
    pass
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
    pass
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
    pass
value = None
match value:
    case Point():
        result = 'branch_0'
    case Point(kind=None, x='red'):
        result = 'branch_1'
    case 3.5,:
        result = 'branch_2'
    case _:
        result = 'default'\
"""
    )


def test_generated_match_patterns_round_trip_through_unmatchify():
    for program in generated_programs(count=80, seed=20260623):
        assert_round_trips(program.to_match_code())
