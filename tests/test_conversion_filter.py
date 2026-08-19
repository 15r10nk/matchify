from textwrap import dedent

import pytest

from matchify.assumptions import Assumptions
from matchify.conversion_filter import ConversionFilter, ConversionMetrics
from matchify.transform import transform_code


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
        "and patterns == 2 and guard_conditions == 0 and captures == 0"
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
