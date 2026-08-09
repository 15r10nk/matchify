from __future__ import annotations

from dataclasses import dataclass

from code_sample_runtime import Trace
from matchify import Assumptions
from matchify.assumptions import parse_assumption_names

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


class SampleFormatError(ValueError):
    pass


def parse_sample(source: str) -> Sample:
    if source.count(BEFORE_MARKER) != 1:
        raise SampleFormatError("sample needs exactly one '# before:' marker")
    if source.count(AFTER_MARKER) != 1:
        raise SampleFormatError("sample needs exactly one '# after:' marker")
    prefix, remainder = source.split(BEFORE_MARKER)
    before, generated = remainder.split(AFTER_MARKER)
    assume_lines = [
        line for line in generated.splitlines() if line.startswith(ASSUME_MARKER)
    ]
    if len(assume_lines) != 1:
        raise SampleFormatError("sample needs exactly one '# assume:' line")
    names = parse_assumption_names(assume_lines[0].removeprefix(ASSUME_MARKER))
    ignore_types_lines = [
        line for line in generated.splitlines() if line.startswith(IGNORE_TYPES_MARKER)
    ]
    if len(ignore_types_lines) > 1:
        raise SampleFormatError("sample allows at most one '# ignore-types:' line")
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


def render_trace(trace: Trace) -> str:
    rendered = "".join(f"# {line}\n" for line in trace.stdout.splitlines())
    if trace.stderr:
        rendered += "# stderr:\n"
        rendered += "".join(f"# {line}\n" for line in trace.stderr.splitlines())
    if trace.exception is not None:
        rendered += f"# exception: {trace.exception.__name__}\n"
        rendered += f"# exception-args: {trace.exception_args!r}\n"
    return rendered


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
