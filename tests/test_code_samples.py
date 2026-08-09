from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pytest
from inline_snapshot import external_file

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


@dataclass(frozen=True)
class Trace:
    stdout: str
    stderr: str
    exception: type[BaseException] | None
    exception_args: tuple[object, ...] | None


def sample_paths() -> list[Path]:
    return sorted(SAMPLES_DIR.glob("*.py"))


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


def execute(source: str) -> Trace:
    stdout = StringIO()
    stderr = StringIO()
    exception = None
    exception_args = None
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(source, {})
    except BaseException as error:
        exception = type(error)
        exception_args = error.args
    return Trace(stdout.getvalue(), stderr.getvalue(), exception, exception_args)


def render_sample(sample: Sample, after: str, trace: Trace) -> str:
    assumption_names = ",".join(sorted(sample.assumptions.names))
    assume_comment = ASSUME_MARKER
    if assumption_names:
        assume_comment += f" {assumption_names}"
    ignore_types_comment = ""
    if sample.ignore_types_pattern is not None:
        ignore_types_comment = f"\n{IGNORE_TYPES_MARKER} {sample.ignore_types_pattern}"
    trace_lines = "".join(f"# {line}\n" for line in trace.stdout.splitlines())
    normalized_after = after.rstrip("\n")
    return (
        f"{sample.prefix}{BEFORE_MARKER}{sample.before}{AFTER_MARKER}"
        f"{normalized_after}\n\n{assume_comment}{ignore_types_comment}"
        f"\n\n# trace:\n{trace_lines}"
    )


def test_execute_records_exception_args():
    trace = execute("raise ValueError('details', 42)")

    assert trace.exception is ValueError
    assert trace.exception_args == ("details", 42)


@pytest.mark.parametrize("sample_path", sample_paths(), ids=lambda path: path.stem)
def test_code_sample(sample_path: Path):
    sample = parse_sample(sample_path.read_text(encoding="utf-8"))
    before = sample.prefix + sample.before
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
