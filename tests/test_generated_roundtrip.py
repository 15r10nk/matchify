from __future__ import annotations

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from matchify.cli import convert_file

SAMPLES_DIR = Path(__file__).parent / "samples"


def sample_dirs() -> list[Path]:
    if not SAMPLES_DIR.exists():
        return []
    return sorted(
        path
        for path in SAMPLES_DIR.iterdir()
        if path.is_dir()
        and (path / "original.py").exists()
        and (path / "converted.py").exists()
        and (path / "trace.txt").exists()
    )


def execute_result(source: str) -> tuple[str, str, type[BaseException] | None]:
    stdout = StringIO()
    stderr = StringIO()
    exception_type = None
    namespace: dict[str, object] = {}
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(source, namespace)
    except BaseException as error:
        exception_type = type(error)
    return (
        str(namespace.get("result")),
        stdout.getvalue() + stderr.getvalue(),
        exception_type,
    )


def exception_name(exception_type: type[BaseException] | None) -> str:
    return "None" if exception_type is None else exception_type.__name__


def format_trace(trace: tuple[str, str, type[BaseException] | None]) -> str:
    return "\n".join(
        [
            f"result: {trace[0]}",
            f"output: {trace[1]!r}",
            f"exception: {exception_name(trace[2])}",
            "",
        ]
    )


@pytest.mark.parametrize("sample_dir", sample_dirs(), ids=lambda path: path.name)
def test_generated_roundtrip_sample(sample_dir: Path, tmp_path: Path):
    original = (sample_dir / "original.py").read_text(encoding="utf-8")
    expected_converted = (sample_dir / "converted.py").read_text(encoding="utf-8")
    expected_trace = (sample_dir / "trace.txt").read_text(encoding="utf-8")
    meta_path = sample_dir / "meta.json"
    meta = (
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    )

    path = tmp_path / "sample.py"
    path.write_text(original, encoding="utf-8")

    converted_path, changed, error = convert_file(path)

    assert converted_path == path
    assert error is None
    assert changed == (meta.get("kind") != "not-converted")

    converted = path.read_text(encoding="utf-8")
    assert converted == expected_converted
    assert format_trace(execute_result(original)) == expected_trace
    assert format_trace(execute_result(converted)) == expected_trace
    match_reference = sample_dir / "match_reference.py"
    if match_reference.exists():
        assert (
            format_trace(execute_result(match_reference.read_text(encoding="utf-8")))
            == expected_trace
        )
