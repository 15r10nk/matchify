"""Dictionary lookup transformations through Matchify's public API."""

from textwrap import dedent

from inline_snapshot import snapshot

from matchify import Assumptions, transform_code
from matchify.assumptions import AssumptionDiagnostic

LOOKUP = Assumptions.from_names({"lookup-equality"})


def test_inline_lookup_in_arbitrary_statement():
    source = 'consume({"create": "POST", "read": "GET"}[operation])'

    assert transform_code(source, assumptions=LOOKUP) == snapshot(
        """\
match operation:
    case "create":
        consume("POST")
    case "read":
        consume("GET")
    case _matchify_key:
        raise KeyError(_matchify_key)\
"""
    )


def test_lookup_comments_remain_before_the_generated_match():
    source = dedent(
        """
        # lookup comment
        print({"create": "POST", "read": "GET"}[operation])
        """
    ).strip()

    assert transform_code(source, assumptions=LOOKUP) == snapshot(
        """\
# lookup comment
match operation:
    case "create":
        print("POST")
    case "read":
        print("GET")
    case _matchify_key:
        raise KeyError(_matchify_key)\
"""
    )


def test_lookup_values_can_be_arbitrary_expressions():
    source = dedent(
        """
        result = {
            "call": make_value(),
            "attribute": settings.value,
            "containers": [1, {"nested": key}],
            "expression": left + right,
        }[key]
        """
    ).strip()

    assert transform_code(source, assumptions=LOOKUP) == snapshot(
        """\
match key:
    case "call":
        result = make_value()
    case "attribute":
        result = settings.value
    case "containers":
        result = [1, {"nested": key}]
    case "expression":
        result = left + right
    case _matchify_key:
        raise KeyError(_matchify_key)\
"""
    )


def test_only_the_chained_lookup_is_excluded():
    source = 'print({"create": {"POST": "a"}, "read": {"GET": "b"}}[a], ' "{}[a][b])"

    transformed = transform_code(source, assumptions=LOOKUP)

    assert transformed == snapshot(
        """\
match a:
    case "create":
        print({"POST": "a"}, {}[a][b])
    case "read":
        print({"GET": "b"}, {}[a][b])
    case _matchify_key:
        raise KeyError(_matchify_key)\
"""
    )
    assert transform_code(transformed, assumptions=LOOKUP) == transformed


def test_function_local_lookup_assignment_is_removed():
    source = dedent(
        """
        def method(operation):
            methods = {"create": "POST", "read": "GET"}
            return methods[operation]
        """
    ).strip()

    assert transform_code(source, assumptions=LOOKUP) == snapshot(
        """\
def method(operation):
    match operation:
        case "create":
            return "POST"
        case "read":
            return "GET"
        case _matchify_key:
            raise KeyError(_matchify_key)\
"""
    )


def test_lookup_requires_assumption_and_reports_it():
    source = 'return {"a": 1}[key]'
    diagnostics: list[AssumptionDiagnostic] = []

    assert transform_code(source, diagnostics=diagnostics) == source
    assert diagnostics == [AssumptionDiagnostic(1, 0, frozenset({"lookup-equality"}))]


def test_local_lookup_requires_assumption_and_one_line_functions_are_ignored():
    source = 'def lookup(key):\n    methods = {"a": 1}\n    return methods[key]'
    diagnostics: list[AssumptionDiagnostic] = []

    assert transform_code(source, diagnostics=diagnostics) == source
    assert diagnostics == [AssumptionDiagnostic(1, 0, frozenset({"lookup-equality"}))]
    assert transform_code("def compact(): return 1", assumptions=LOOKUP) == (
        "def compact(): return 1"
    )


def test_subject_is_evaluated_once_and_missing_key_is_preserved():
    source = dedent(
        """
        calls = 0
        def subject():
            global calls
            calls += 1
            return "missing"

        try:
            result = {"a": 1}[subject()]
        except KeyError as error:
            missing = error.args[0]
        """
    ).strip()
    transformed = transform_code(source, assumptions=LOOKUP)
    namespace: dict[str, object] = {}

    assert transformed == snapshot(
        """\
calls = 0
def subject():
    global calls
    calls += 1
    return "missing"

try:
    match subject():
        case "a":
            result = 1
        case _matchify_key:
            raise KeyError(_matchify_key)
except KeyError as error:
    missing = error.args[0]\
"""
    )
    exec(transformed, namespace)

    assert namespace["calls"] == 1
    assert namespace["missing"] == "missing"


def test_unsafe_lookup_tables_remain_unchanged():
    sources = (
        'return {**other, "a": 1}[key]',
        'return {1: "integer", True: "boolean"}[key]',
        "return {name: 1}[key]",
        "return {Token.A: 1}[key]",
        'return {"a": 1}[start:stop]',
        'return {"a": 1}[key, other]',
        'return {"a": 1}[key] + {"b": 2}[key]',
        'return {"a": {"nested": 1}}[key][nested_key]',
    )

    for source in sources:
        assert transform_code(source, assumptions=LOOKUP) == source


def test_nonlocal_and_reused_lookup_variables_remain_unchanged():
    module_source = 'methods = {"a": 1}\nresult = methods[key]'
    reused_source = dedent(
        """
        def lookup(key):
            methods = {"a": 1}
            inspect(methods)
            return methods[key]
        """
    ).strip()

    assert transform_code(module_source, assumptions=LOOKUP) == module_source
    assert transform_code(reused_source, assumptions=LOOKUP) == reused_source


def test_invalid_local_lookup_uses_and_capture_name_collisions():
    invalid_slice = dedent(
        """
        def lookup(key):
            methods = {"a": 1}
            return methods[:]
        """
    ).strip()
    use_before_assignment = dedent(
        """
        def lookup(key):
            return methods[key]
            methods = {"a": 1}
        """
    ).strip()
    source = '_matchify_key = {"a": 1}[key]'

    assert transform_code(invalid_slice, assumptions=LOOKUP) == invalid_slice
    assert transform_code(use_before_assignment, assumptions=LOOKUP) == (
        use_before_assignment
    )
    assert transform_code(source, assumptions=LOOKUP) == snapshot(
        """\
match key:
    case "a":
        _matchify_key = 1
    case _matchify_key_2:
        raise KeyError(_matchify_key_2)\
"""
    )
