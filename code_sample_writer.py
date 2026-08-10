from __future__ import annotations

from pathlib import Path

from code_sample_format import Sample, render_sample
from code_sample_runtime import Trace
from matchify import Assumptions


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
    sample_path.write_text(
        render_sample(
            Sample(
                prefix=header,
                before=f"{before.rstrip()}\n\n",
                assumptions=Assumptions.from_names(),
                ignore_types_pattern=None,
            ),
            after,
            trace,
        ),
        encoding="utf-8",
    )
    return sample_path
