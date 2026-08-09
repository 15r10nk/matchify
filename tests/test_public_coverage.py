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


def test_nested_subscription_without_sequence_anchor_stays_in_guard():
    source = dedent(
        """\
        if value[0][0] == 1:
            result = "one"
        elif value is None:
            result = "none"
        """
    )

    transformed = transform_code(source)

    assert "case _ if value[0][0] == 1:" in transformed
    for value in ([[1]], [[2]], None, [], [[]]):
        outcomes = []
        for code in (source, transformed):
            namespace = {"value": value}
            try:
                exec(code, namespace)
            except (IndexError, TypeError) as error:
                outcomes.append(type(error))
            else:
                outcomes.append(namespace.get("result"))
        assert outcomes[0] == outcomes[1]
