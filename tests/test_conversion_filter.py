import pickle
from textwrap import dedent

import libcst as cst
import pytest

from matchify.conversion_filter import (
    ConversionFilter,
    ConversionMetrics,
    with_generated_metrics,
)
from matchify.transform import collect_chain_previews


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
    source = dedent(f"""\
        if {condition}:
            first()
        elif value == 0:
            second()
        """)
    expression = f"value_patterns == {expected}"

    preview = collect_chain_previews(source, convert_if=expression)[0]
    assert preview.metrics.value_patterns == expected


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
    source = dedent(f"""\
        if {condition}:
            first()
        elif value == 0:
            second()
        """)
    expression = f"self_value_patterns == {expected}"
    preview = collect_chain_previews(source, convert_if=expression)[0]
    assert preview.metrics.self_value_patterns == expected


def test_maximum_pattern_depth_covers_all_pattern_containers():
    module = cst.parse_module(dedent("""
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
            """))
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
