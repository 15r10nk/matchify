from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from inline_snapshot import external_file

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from code_sample_runtime import Trace, execute
from code_sample_writer import render_trace
from matchify import Assumptions, transform_code
from matchify.assumptions import parse_assumption_names

SAMPLES_DIR = Path(__file__).parent / "code_samples"
BEFORE_MARKER = "# before:\n"
AFTER_MARKER = "# after:\n"
ASSUME_MARKER = "# assume:"
IGNORE_TYPES_MARKER = "# ignore-types:"


@dataclass(frozen=True)
class Sample:
    prefix: str
    before: str
    assumptions: Assumptions
    ignore_types_pattern: str | None


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


def parse_sample(source: str) -> Sample:
    assert source.count(BEFORE_MARKER) == 1
    assert source.count(AFTER_MARKER) == 1
    prefix, remainder = source.split(BEFORE_MARKER)
    before, generated = remainder.split(AFTER_MARKER)
    assume_lines = [
        line for line in generated.splitlines() if line.startswith(ASSUME_MARKER)
    ]
    assert len(assume_lines) == 1
    names = parse_assumption_names(assume_lines[0].removeprefix(ASSUME_MARKER))
    ignore_types_lines = [
        line for line in generated.splitlines() if line.startswith(IGNORE_TYPES_MARKER)
    ]
    assert len(ignore_types_lines) <= 1
    ignore_types_pattern = None
    if ignore_types_lines:
        ignore_types_pattern = (
            ignore_types_lines[0].removeprefix(IGNORE_TYPES_MARKER).strip() or None
        )
    return Sample(
        prefix,
        before,
        Assumptions.from_names(names),
        ignore_types_pattern,
    )


def render_sample(sample: Sample, after: str, trace: Trace) -> str:
    assumption_names = ",".join(sorted(sample.assumptions.names))
    assume_comment = ASSUME_MARKER
    if assumption_names:
        assume_comment += f" {assumption_names}"
    ignore_types_comment = ""
    if sample.ignore_types_pattern is not None:
        ignore_types_comment = f"\n{IGNORE_TYPES_MARKER} {sample.ignore_types_pattern}"
    normalized_after = after.rstrip("\n")
    return (
        f"{sample.prefix}{BEFORE_MARKER}{sample.before}{AFTER_MARKER}"
        f"{normalized_after}\n\n{assume_comment}{ignore_types_comment}"
        f"\n\n# trace:\n{render_trace(trace)}"
    )


def test_execute_records_exception_args():
    trace = execute("raise ValueError('details', 42)")

    assert trace.exception is ValueError
    assert trace.exception_args == ("details", 42)


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
