"""Coverage cases exercised exclusively through Matchify's public API."""

from textwrap import dedent

from matchify import Assumptions, transform_code


def test_rejects_dynamic_and_non_string_hasattr_names():
    source = dedent(
        r"""
        value = object()
        name = "field"
        if hasattr(value, name):
            result = "dynamic"
        elif hasattr(value, b"field"):
            result = "bytes"
        """
    ).strip()

    assert transform_code(source) == source


def test_rejects_non_literal_and_starred_membership_containers():
    source = dedent(
        """
        values = (1, 2)
        value = 1
        if value in values:
            result = "dynamic"
        elif value in (*values,):
            result = "starred"
        """
    ).strip()

    assert transform_code(source) == source


def test_single_literal_membership_becomes_a_value_pattern():
    source = dedent(
        """
        value = 1
        if value in (1,):
            result = "one"
        elif value in (2,):
            result = "two"
        """
    ).strip()

    transformed = transform_code(source)

    assert "match value:" in transformed
    assert "case 1:" in transformed
    assert "case 2:" in transformed


def test_rejects_unsafe_equality_on_a_selected_subject():
    source = dedent(
        """
        value = 1
        if value == 1 and value == factory():
            result = "first"
        elif value == 2 and value == factory():
            result = "second"
        """
    ).strip()

    assert transform_code(source) == source


def test_rejects_unsafe_identity_on_a_selected_subject():
    source = dedent(
        """
        value = 1
        if value == 1 and value is marker:
            result = "first"
        elif value == 2 and value is marker:
            result = "second"
        """
    ).strip()

    assert transform_code(source) == source


def test_conflicting_value_facts_fall_back_to_a_guard():
    source = dedent(
        """
        value = 1
        if value == 1 and value == 2:
            result = "impossible"
        elif value == 3:
            result = "three"
        else:
            result = "other"
        """
    ).strip()

    assert transform_code(source) == source


def test_subscript_or_expression_does_not_hide_a_later_value_subject():
    source = dedent(
        """
        value = 3
        if (value[0] == 1 or value[1] == 2) and value == 3:
            result = "three"
        elif value == 4:
            result = "four"
        """
    ).strip()

    transformed = transform_code(source)

    assert "match value:" in transformed
    assert "case 3 if (value[0] == 1 or value[1] == 2):" in transformed


def test_incompatible_class_and_subscript_facts_are_rejected():
    source = dedent(
        """
        if isinstance(value, First) and value[0] == 1:
            result = "first"
        elif isinstance(value, Second) and value[0] == 2:
            result = "second"
        """
    ).strip()

    assert transform_code(source) == source


def test_redundant_sequence_type_guards_are_dropped_from_or_patterns():
    source = dedent(
        """
        if (isinstance(value, (list, tuple)) and len(value) == 1) or (isinstance(value, (list, tuple)) and len(value) == 2):
            result = "sequence"
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_code(
        source,
        assumptions=Assumptions.from_names(
            {"list-sequence-pattern", "tuple-sequence-pattern"}
        ),
    )

    assert "case [_] | [_, _]:" in transformed
    assert "case None:" in transformed


def test_or_alternatives_with_different_guards_fall_back_to_a_guard():
    source = dedent(
        """
        if (value == 1 and first_flag) or (value == 2 and second_flag):
            result = "flagged"
        elif value == 3:
            result = "three"
        """
    ).strip()

    transformed = transform_code(source)

    assert (
        "case _ if (value == 1 and first_flag) or (value == 2 and second_flag):"
        in transformed
    )


def test_nested_or_fact_with_a_shared_guard_is_rendered():
    source = dedent(
        """
        if ((value == 1 or value == 2) and enabled) or (value == 3 and enabled):
            result = "enabled"
        elif value == 4:
            result = "four"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case 1 | 2 | 3 if enabled:" in transformed


def test_capture_stays_in_body_when_class_attribute_is_not_patterned():
    source = dedent(
        """
        if isinstance(value, First):
            item = value.items[0]
            result = item
        elif isinstance(value, Second):
            result = "second"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case First():" in transformed
    assert "item = value.items[0]" in transformed


def test_capture_stays_in_body_for_an_incompatible_attribute_parent():
    source = dedent(
        """
        if len(value) == 1 and value[0] == 1:
            item = value.items[0]
            result = item
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case 1,:" in transformed
    assert "item = value.items[0]" in transformed


def test_nested_capture_stays_in_body_when_the_child_is_not_a_sequence():
    source = dedent(
        """
        if isinstance(value, First) and value.items == 1:
            item = value.items[0]
            result = item
        elif isinstance(value, Second) and value.items == 2:
            result = "second"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case First(items=1):" in transformed
    assert "item = value.items[0]" in transformed


def test_deep_capture_stays_in_body_when_intermediate_element_is_missing():
    source = dedent(
        """
        if len(value) == 2 and value[1] == 1:
            item = value[0][0]
            result = item
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case _, 1:" in transformed
    assert "item = value[0][0]" in transformed


def test_capture_stays_in_body_when_only_one_or_alternative_can_bind():
    source = dedent(
        """
        if (len(value) == 2 and value[1] == 1) or value == 0:
            item = value[0]
            result = item
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case [_, 1] | 0:" in transformed
    assert "item = value[0]" in transformed


def test_accepts_deeply_qualified_class_patterns():
    source = dedent(
        """
        value = None
        if isinstance(value, package.models.First):
            result = "first"
        elif isinstance(value, package.models.Second):
            result = "second"
        """
    ).strip()

    transformed = transform_code(source)

    assert "match value:" in transformed
    assert "case package.models.First():" in transformed
    assert "case package.models.Second():" in transformed


def test_duplicate_capture_with_multiple_remaining_statements():
    source = dedent(
        """
        value = [1, 2]
        if len(value) == 2 and value[1] == 2:
            first = value[0]
            duplicate = value[0]
            result = first
            print(result)
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_code(source)

    assert "case first, 2:" in transformed
    assert "duplicate = first" in transformed
    assert "result = first" in transformed
    assert "print(result)" in transformed
