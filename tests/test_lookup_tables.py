"""Dictionary lookup transformations through Matchify's public API."""

from matchify import transform_code
from matchify.assumptions import AssumptionDiagnostic


def test_lookup_requires_assumption_and_reports_it():
    source = 'return {"a": 1}[key]'
    diagnostics: list[AssumptionDiagnostic] = []

    assert transform_code(source, diagnostics=diagnostics) == source
    assert diagnostics == [AssumptionDiagnostic(1, 0, frozenset({"lookup-equality"}))]


def test_local_lookup_requires_assumption():
    source = 'def lookup(key):\n    methods = {"a": 1}\n    return methods[key]'
    diagnostics: list[AssumptionDiagnostic] = []

    assert transform_code(source, diagnostics=diagnostics) == source
    assert diagnostics == [AssumptionDiagnostic(1, 0, frozenset({"lookup-equality"}))]
