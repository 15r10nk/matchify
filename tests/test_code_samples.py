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


@dataclass(frozen=True)
class Sample:
    prefix: str
    before: str
    assumptions: Assumptions


@dataclass(frozen=True)
class Trace:
    stdout: str
    stderr: str
    exception: type[BaseException] | None


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
    return Sample(prefix, before, Assumptions.from_names(names))


def execute(source: str) -> Trace:
    stdout = StringIO()
    stderr = StringIO()
    exception = None
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(source, {})
    except BaseException as error:
        exception = type(error)
    return Trace(stdout.getvalue(), stderr.getvalue(), exception)


def render_sample(sample: Sample, after: str, trace: Trace) -> str:
    assumption_names = ",".join(sorted(sample.assumptions.names))
    assume_comment = ASSUME_MARKER
    if assumption_names:
        assume_comment += f" {assumption_names}"
    trace_lines = "".join(f"# {line}\n" for line in trace.stdout.splitlines())
    normalized_after = after.rstrip("\n")
    return (
        f"{sample.prefix}{BEFORE_MARKER}{sample.before}{AFTER_MARKER}"
        f"{normalized_after}\n\n{assume_comment}"
        f"\n\n# trace:\n{trace_lines}"
    )


@pytest.mark.parametrize("sample_path", sample_paths(), ids=lambda path: path.stem)
def test_code_sample(sample_path: Path):
    sample = parse_sample(sample_path.read_text(encoding="utf-8"))
    before = sample.prefix + sample.before
    transformed = transform_code(before, assumptions=sample.assumptions)
    assert transformed.startswith(sample.prefix)
    after = transformed.removeprefix(sample.prefix)
    before_trace = execute(before)
    after_trace = execute(sample.prefix + after)

    assert before_trace == after_trace
    assert render_sample(sample, after, after_trace) == external_file(
        sample_path, format=".txt"
    )
