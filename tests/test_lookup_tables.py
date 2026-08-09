"""Dictionary lookup transformations through Matchify's public API."""

from textwrap import dedent

from inline_snapshot import snapshot

from matchify import Assumptions, transform_code
from matchify.assumptions import AssumptionDiagnostic

LOOKUP = Assumptions.from_names({"lookup-equality"})


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
