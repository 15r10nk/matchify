import io
from contextlib import redirect_stderr, redirect_stdout

from matchify.transform import transform_code


def check_code(
    source: str, expected: str, ignore_types_pattern: str | None = r".*_TYPES$"
) -> None:
    """
    Test helper that:
    1. Transforms source code using transform_code
    2. Verifies the transformed code matches expected output
    3. Executes both source and expected code and verifies identical output
    """
    # Transform the source code
    transformed_code = transform_code(source, ignore_types_pattern=ignore_types_pattern)

    # Check transformation matches expected
    assert transformed_code.strip() == expected.strip(), (
        f"Transformation mismatch:\n"
        f"Expected:\n{expected}\n\n"
        f"Got:\n{transformed_code}"
    )

    # Execute both code snippets in the same process and capture output
    # Execute original source
    stdout_source = io.StringIO()
    stderr_source = io.StringIO()
    exception_source = None
    try:
        with redirect_stdout(stdout_source), redirect_stderr(stderr_source):
            exec(source, {})
    except Exception as e:
        exception_source = e

    # Execute expected (transformed) code
    stdout_expected = io.StringIO()
    stderr_expected = io.StringIO()
    exception_expected = None
    try:
        with redirect_stdout(stdout_expected), redirect_stderr(stderr_expected):
            exec(expected, {})
    except Exception as e:
        exception_expected = e

    # Verify both produce the same output
    assert stdout_source.getvalue() == stdout_expected.getvalue(), (
        f"Output mismatch:\n"
        f"Source output:\n{stdout_source.getvalue()}\n"
        f"Expected output:\n{stdout_expected.getvalue()}"
    )

    assert stderr_source.getvalue() == stderr_expected.getvalue(), (
        f"Error output mismatch:\n"
        f"Source stderr:\n{stderr_source.getvalue()}\n"
        f"Expected stderr:\n{stderr_expected.getvalue()}"
    )

    # Verify both have the same exception behavior
    assert type(exception_source) == type(exception_expected), (
        f"Exception mismatch:\n"
        f"Source exception: {exception_source}\n"
        f"Expected exception: {exception_expected}"
    )
