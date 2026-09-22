import pickle
from textwrap import dedent

import libcst as cst
import pytest

from matchify.assumptions import Assumptions
from matchify.conversion_filter import (
    ConversionFilter,
    ConversionMetrics,
    with_generated_metrics,
)
from matchify.transform import collect_chain_previews, transform_code


@pytest.mark.parametrize(
    "expression",
    [
        "min(branches, 2) > 1",
        "branches in (2, 3)",
        "branches.bit_length() > 1",
        "branches[0] > 1",
        "'2' == branches",
        "branches // 2 > 1",
        "branches % 2 == 0",
        "branches**2 > 1",
        "-branches < 0",
        "False and __import__('os')",
        "(lambda: True)()",
    ],
)
def test_conversion_filter_rejects_unsupported_syntax(expression):
    with pytest.raises(ValueError, match="Unsupported syntax"):
        ConversionFilter.parse(expression)


def test_conversion_filter_reports_unknown_names():
    with pytest.raises(ValueError, match="Unknown --convert-if variable: branch"):
        ConversionFilter.parse("branch > 2")


def test_conversion_filter_reports_invalid_syntax():
    with pytest.raises(ValueError, match="Invalid --convert-if expression"):
        ConversionFilter.parse("branches >")


def test_conversion_filter_supports_agreed_operators_and_truthiness():
    metrics = ConversionMetrics(branches=3, guard_conditions=0, max_depth=2)

    assert ConversionFilter.parse(
        "branches >= 3 and branches <= 4 and max_depth != 1 and not guard_conditions"
    ).matches(metrics)
    assert (
        ConversionFilter.parse(
            "branches < 2 or branches > 4 or max_depth == 1"
        ).matches(metrics)
        is False
    )


@pytest.mark.parametrize(("expression", "expected"), [("True", True), ("False", False)])
def test_conversion_filter_supports_boolean_constants(expression, expected):
    assert ConversionFilter.parse(expression).matches(ConversionMetrics()) is expected


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("(branches or 1) == 2", True),
        ("(guard_conditions or branches) == 2", True),
        ("(branches and 4) == 4", True),
        ("(branches or 1) == 1", False),
        ("branches or 1 / 0", True),
        ("guard_conditions and 1 / 0", False),
        ("branches < 1 < 1 / 0", False),
    ],
)
def test_filter_preserves_python_boolean_semantics(expression, expected):
    source = dedent(
        """
        if value == 1:
            pass
        elif value == 2:
            pass
        """
    )

    transformed = transform_code(source, convert_if=expression)

    if expected:
        assert "match value:" in transformed
    else:
        assert transformed == source


def test_conversion_filter_remains_picklable_after_evaluation():
    conversion_filter = ConversionFilter.parse("(branches or 1) == 3")
    metrics = ConversionMetrics(branches=3)

    assert conversion_filter.matches(metrics)
    restored = pickle.loads(pickle.dumps(conversion_filter))

    assert restored.matches(metrics)
    assert not restored.matches(ConversionMetrics(branches=2))


def test_conversion_filter_supports_arithmetic_with_python_precedence():
    metrics = ConversionMetrics(branches=4, patterns=3, guard_conditions=1)

    assert ConversionFilter.parse("patterns + guard_conditions / branches > 3").matches(
        metrics
    )
    assert ConversionFilter.parse(
        "(patterns + guard_conditions) / branches == 1 "
        "and branches - guard_conditions == patterns "
        "and guard_conditions * branches == branches"
    ).matches(metrics)


def test_conversion_filter_division_by_zero_is_not_silenced():
    with pytest.raises(ZeroDivisionError):
        ConversionFilter.parse("branches / 0 > 1").matches(
            ConversionMetrics(branches=3)
        )


def test_filter_can_select_using_all_source_and_result_metrics():
    source = dedent(
        """
        class Point:
            pass

        if isinstance(value, Point) and value.x == 1:
            print("one")
        elif isinstance(value, Point) and value.x == 2:
            print("two")
        """
    ).strip()
    expression = (
        "branches == 2 and isinstance_checks == 2 and literal_checks == 2 "
        "and attribute_checks == 2 and sequence_checks == 0 and max_depth == 1 "
        "and patterns == 2 and pattern_nodes == 4 and value_patterns == 0 "
        "and self_value_patterns == 0 and class_patterns == 2 "
        "and sequence_patterns == 0 and or_alternatives == 0 "
        "and max_pattern_depth == 2 and guarded_cases == 0 "
        "and guard_conditions == 0 and captures == 0"
    )

    assert "match value:" in transform_code(source, convert_if=expression)
    assert transform_code(source, convert_if=f"not ({expression})") == source


def test_filter_counts_sequence_checks_guards_and_captures():
    source = dedent(
        """
        if len(data) == 2 and data[0] == 1 and enabled and ready:
            result = data[1]
            print(result)
        elif len(data) == 2 and data[0] == 2 and enabled and ready:
            result = data[1]
            print(result)
        """
    ).strip()

    transformed = transform_code(
        source,
        convert_if="sequence_checks == 2 and guard_conditions == 4 and captures == 2",
    )

    assert "match data:" in transformed
    assert "case 1, result if enabled and ready:" in transformed


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("value == self.val", 1),
        ("value in (self.val, package.Kind.OTHER)", 2),
        ("value == 1 and check(self.val)", 0),
        ("isinstance(value, package.Thing)", 0),
        ('value == "text"', 0),
        ("value is None", 0),
    ],
)
def test_filter_counts_qualified_value_patterns(condition, expected):
    source = dedent(
        f"""\
        if {condition}:
            first()
        elif value == 0:
            second()
        """
    )
    expression = f"value_patterns == {expected}"

    assert "match value:" in transform_code(source, convert_if=expression)
    assert transform_code(source, convert_if=f"not ({expression})") == source
    preview = collect_chain_previews(source, convert_if=expression)[0]
    assert preview.metrics.value_patterns == expected


def test_filter_counts_qualified_value_patterns_inside_composite_patterns():
    source = dedent(
        """\
        if left == self.val and right == Kind.OTHER:
            first()
        elif left == 1 and right == 2:
            second()
        """
    )
    transformed = transform_code(
        source,
        assumptions=Assumptions.PURE_SUBJECTS,
        convert_if="value_patterns == 2 and self_value_patterns == 1",
    )
    assert "case self.val, Kind.OTHER:" in transformed


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        ("value == self.val", 1),
        ("value == self.settings.val", 1),
        ("value == other.val", 0),
        ("value == other.self.val", 0),
        ("value == selfish.val", 0),
        ("value in (self.val, other.val, self.other)", 2),
        ("value == 1 and check(self.val)", 0),
        ("isinstance(value, self.Kind)", 0),
    ],
)
def test_filter_distinguishes_self_value_patterns(condition, expected):
    source = dedent(
        f"""\
        if {condition}:
            first()
        elif value == 0:
            second()
        """
    )
    expression = f"self_value_patterns == {expected}"
    assert "match value:" in transform_code(source, convert_if=expression)
    assert transform_code(source, convert_if=f"not ({expression})") == source
    preview = collect_chain_previews(source, convert_if=expression)[0]
    assert preview.metrics.self_value_patterns == expected


def test_filter_counts_names_once_across_or_pattern_alternatives():
    source = dedent(
        """
        if (len(value) >= 3 and value[1] == 2) or (len(value) >= 3 and value[1] == 3):
            first = value[0]
            third = value[2]
            print(first, third)
        elif value is None:
            print("none")
        """
    ).strip()

    transformed = transform_code(source, convert_if="captures == 2")

    assert "case [first, 2, third, *_] | [first, 3, third, *_]:" in transformed


def test_filter_counts_maximum_generated_pattern_depth():
    source = dedent(
        """
        if isinstance(node, Point) and isinstance(node.position, Position) and node.position.x == 1:
            print("one")
        elif isinstance(node, Point) and isinstance(node.position, Position) and node.position.x == 2:
            print("two")
        """
    ).strip()

    assert "match node:" in transform_code(source, convert_if="max_pattern_depth == 3")
    assert transform_code(source, convert_if="max_pattern_depth < 3") == source


def test_maximum_pattern_depth_covers_all_pattern_containers():
    module = cst.parse_module(
        dedent(
            """
            match value:
                case Point(position=Position(x=1)) if enabled:
                    pass
                case [1 | 2, {"key": captured}] as whole:
                    pass
                case [1, *rest]:
                    pass
                case {"key": 1, **remaining}:
                    pass
                case Wrapper(Point()):
                    pass
                case _:
                    pass
            """
        )
    )
    match_statement = module.body[0]
    assert isinstance(match_statement, cst.Match)

    metrics = with_generated_metrics(ConversionMetrics(), match_statement)

    assert metrics.max_pattern_depth == 4
    assert metrics.pattern_nodes == 17
    assert metrics.class_patterns == 4
    assert metrics.sequence_patterns == 2
    assert metrics.or_alternatives == 2
    assert metrics.guarded_cases == 1
    assert metrics.captures == 4


def test_filter_runs_after_assumption_resolution():
    source = dedent(
        """
        if a.x == 1 and b.y == 2:
            print("first")
        elif a.x == 3 and b.y == 4:
            print("second")
        """
    ).strip()

    transformed = transform_code(
        source,
        assumptions=Assumptions.from_names({"pure-subjects"}),
        convert_if="patterns == 2 and guard_conditions == 0",
    )

    assert "match (a.x, b.y):" in transformed


def test_filter_does_not_apply_to_lookup_conversions():
    source = 'result = {"create": "POST", "read": "GET"}[operation]'

    transformed = transform_code(
        source,
        assumptions=Assumptions.from_names({"lookup-equality"}),
        convert_if="branches > 100",
    )

    assert "match operation:" in transformed
