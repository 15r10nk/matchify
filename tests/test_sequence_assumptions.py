"""Behavior of opt-in sequence type assumptions through the public API."""

from textwrap import dedent

from matchify import Assumptions, transform_code


def transform_with(source: str, *assumptions: str) -> str:
    return transform_code(source, assumptions=Assumptions.from_names(assumptions))


def test_list_check_requires_list_sequence_pattern_assumption():
    source = dedent(
        """
        if isinstance(value, list) and len(value) == 1 and value[0] == 1:
            result = "one"
        elif value is None:
            result = "none"
        """
    ).strip()

    safe = transform_code(source)
    assumed = transform_with(source, "list-sequence-pattern")

    assert "case 1, if isinstance(value, list):" in safe
    assert "case 1,:" in assumed
    assert "if isinstance(value, list)" not in assumed


def test_tuple_check_requires_tuple_sequence_pattern_assumption():
    source = dedent(
        """
        if isinstance(value, tuple) and len(value) == 1 and value[0] == 1:
            result = "one"
        elif value is None:
            result = "none"
        """
    ).strip()

    safe = transform_code(source)
    assumed = transform_with(source, "tuple-sequence-pattern")

    assert "case 1, if isinstance(value, tuple):" in safe
    assert "case 1,:" in assumed
    assert "if isinstance(value, tuple)" not in assumed


def test_list_assumption_does_not_apply_to_tuple_checks():
    source = dedent(
        """
        if isinstance(value, tuple) and len(value) == 1 and value[0] == 1:
            result = "one"
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_with(source, "list-sequence-pattern")

    assert "case 1, if isinstance(value, tuple):" in transformed


def test_sequence_assumptions_do_not_apply_to_qualified_class_checks():
    source = dedent(
        """
        if isinstance(value, (list, types.TupleType)) and len(value) == 1:
            result = "one"
        elif value is None:
            result = "none"
        """
    ).strip()

    transformed = transform_with(
        source,
        "list-sequence-pattern",
        "tuple-sequence-pattern",
    )

    assert "if isinstance(value, (list, types.TupleType))" in transformed


def test_safe_default_preserves_runtime_for_other_sequence_types():
    source = dedent(
        """
        value = range(1)
        result = "other"
        if isinstance(value, (list, tuple)) and len(value) == 1:
            result = "sequence"
        elif value is None:
            result = "none"
        """
    ).strip()
    transformed = transform_code(source)
    original_namespace = {}
    transformed_namespace = {}

    exec(source, original_namespace)
    exec(transformed, transformed_namespace)

    assert original_namespace["result"] == "other"
    assert transformed_namespace["result"] == original_namespace["result"]
