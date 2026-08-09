"""Coverage cases exercised exclusively through Matchify's public API."""

from textwrap import dedent

from matchify import transform_code


def test_sequence_type_guard_preserves_runtime_for_other_sequence_types():
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
