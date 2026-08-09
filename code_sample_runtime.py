from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO


@dataclass(frozen=True)
class Trace:
    stdout: str
    stderr: str
    exception: type[BaseException] | None
    exception_args: tuple[object, ...] | None


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
