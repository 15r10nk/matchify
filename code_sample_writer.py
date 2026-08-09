from __future__ import annotations

from pathlib import Path

from code_sample_runtime import Trace


def render_trace(trace: Trace) -> str:
    rendered = "".join(f"# {line}\n" for line in trace.stdout.splitlines())
    if trace.stderr:
        rendered += "# stderr:\n"
        rendered += "".join(f"# {line}\n" for line in trace.stderr.splitlines())
    if trace.exception is not None:
        rendered += f"# exception: {trace.exception.__name__}\n"
        rendered += f"# exception-args: {trace.exception_args!r}\n"
    return rendered


def save_code_sample(
    *,
    samples_dir: Path,
    sample_id: str,
    before: str,
    after: str,
    trace: Trace,
    metadata: tuple[tuple[str, str | int], ...],
) -> Path:
    """Write a generated issue in the format consumed by test_code_samples.py."""
    if not trace.stdout:
        raise ValueError("code samples require a non-empty stdout trace")

    samples_dir.mkdir(parents=True, exist_ok=True)
    sample_path = samples_dir / f"{sample_id}.py"
    header = "".join(f"# {name}: {value}\n" for name, value in metadata)
    rendered_trace = render_trace(trace)
    sample_path.write_text(
        f"{header}# before:\n{before.rstrip()}\n\n"
        f"# after:\n{after.rstrip()}\n\n"
        f"# assume:\n\n# trace:\n{rendered_trace}",
        encoding="utf-8",
    )
    return sample_path
