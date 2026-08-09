from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
from inline_snapshot import external_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from code_sample_format import (
    SampleFormatError,
    parse_sample,
    render_sample,
    render_trace,
)
from code_sample_runtime import Trace, execute
from matchify import transform_code

SAMPLES_DIR = Path(__file__).parent / "code_samples"


def sample_paths() -> list[Path]:
    return sorted(SAMPLES_DIR.glob("*.py"))


def assert_result_is_observed(source: str) -> None:
    tree = ast.parse(source)
    assigns_result = any(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == "result"
        for node in ast.walk(tree)
    )
    prints_result = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and any(isinstance(arg, ast.Name) and arg.id == "result" for arg in node.args)
        for node in ast.walk(tree)
    )
    assert (
        not assigns_result or prints_result
    ), "a code sample that assigns to 'result' must pass that value directly to print()"


def test_execute_records_exception_args():
    trace = execute("raise ValueError('details', 42)")

    assert trace.exception is ValueError
    assert trace.exception_args == ("details", 42)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("# after:\n# assume:\n", "exactly one '# before:'"),
        ("# before:\n# assume:\n", "exactly one '# after:'"),
        ("# before:\n# after:\n", "exactly one '# assume:'"),
        (
            "# before:\n# after:\n# assume:\n# ignore-types: A\n" "# ignore-types: B\n",
            "at most one '# ignore-types:'",
        ),
    ],
)
def test_parse_sample_reports_invalid_structure(source, message):
    with pytest.raises(SampleFormatError, match=message):
        parse_sample(source)


@pytest.mark.parametrize(
    "source",
    ["result = 'ok'\n", "result = 'ok'\nprint(type(result).__name__)\n"],
)
def test_result_assignments_must_be_observed(source):
    with pytest.raises(AssertionError, match="must pass that value directly"):
        assert_result_is_observed(source)


def test_directly_printed_result_is_observed():
    assert_result_is_observed("result = 'ok'\nprint(result)\n")


def test_render_trace_includes_stderr_and_exception_details():
    trace = Trace("started\n", "warning\n", ValueError, ("details", 42))

    assert render_trace(trace) == (
        "# started\n"
        "# stderr:\n"
        "# warning\n"
        "# exception: ValueError\n"
        "# exception-args: ('details', 42)\n"
    )


@pytest.mark.parametrize("sample_path", sample_paths(), ids=lambda path: path.stem)
def test_code_sample(sample_path: Path):
    sample = parse_sample(sample_path.read_text(encoding="utf-8"))
    before = sample.prefix + sample.before
    assert_result_is_observed(before)
    transformed = transform_code(
        before,
        assumptions=sample.assumptions,
        ignore_types_pattern=sample.ignore_types_pattern,
    )
    assert transformed.startswith(sample.prefix)
    after = transformed.removeprefix(sample.prefix)
    before_trace = execute(before)
    after_trace = execute(sample.prefix + after)

    assert before_trace == after_trace
    assert after_trace.stdout
    assert render_sample(sample, after, after_trace) == external_file(
        sample_path, format=".txt"
    )
