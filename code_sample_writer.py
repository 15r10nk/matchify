from __future__ import annotations

from pathlib import Path


def save_code_sample(
    *,
    samples_dir: Path,
    sample_id: str,
    before: str,
    after: str,
    trace_output: str,
    metadata: tuple[tuple[str, str | int], ...],
) -> Path:
    """Write a generated issue in the format consumed by test_code_samples.py."""
    if not trace_output:
        raise ValueError("code samples require a non-empty stdout trace")

    samples_dir.mkdir(parents=True, exist_ok=True)
    sample_path = samples_dir / f"{sample_id}.py"
    header = "".join(f"# {name}: {value}\n" for name, value in metadata)
    trace = "".join(f"# {line}\n" for line in trace_output.splitlines())
    sample_path.write_text(
        f"{header}# before:\n{before.rstrip()}\n\n"
        f"# after:\n{after.rstrip()}\n\n"
        f"# assume:\n\n# trace:\n{trace}",
        encoding="utf-8",
    )
    return sample_path
