"""Command-line and file processing helpers."""

import argparse
import pathlib
from concurrent.futures import ProcessPoolExecutor
from functools import partial

from .assumptions import (
    ALL_RISKY_ASSUMPTIONS,
    AssumptionDiagnostic,
    Assumptions,
    parse_assumption_names,
)
from .transform import transform_code


def convert_file(
    path: pathlib.Path,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    assume_pure_subjects: bool = False,
    report_assumption_diagnostics: bool = False,
) -> tuple[pathlib.Path, bool, str | None]:
    """Convert a single file.

    Returns:
        Tuple of (path, changed, error_message)
    """
    try:
        source = path.read_text(encoding="utf-8")
        diagnostics: list[AssumptionDiagnostic] = []
        transformed_code = transform_code(
            source,
            ignore_types_pattern=ignore_types_pattern,
            assumptions=assumptions,
            assume_pure_subjects=assume_pure_subjects,
            diagnostics=diagnostics,
        )

        if report_assumption_diagnostics:
            report_assumption_requirements(path, diagnostics)
        if transformed_code != source:
            path.write_text(transformed_code, encoding="utf-8")
            return (path, True, None)
        return (path, False, None)
    except Exception as e:
        return (path, False, str(e))


def collect_python_files(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """Collect all Python files from the given paths."""
    python_files = []
    for arg in paths:
        if arg.is_file() and arg.suffix == ".py":
            python_files.append(arg)
        elif arg.is_dir():
            python_files.extend(arg.rglob("*.py"))
        else:
            print(f"Skipping (not a Python file): {arg}")
    return python_files


def resolve_assumptions(args: argparse.Namespace) -> Assumptions:
    """Resolve CLI assumption flags into an assumption set."""
    if args.risky:
        return Assumptions.risky()
    if args.safe_assumptions:
        return Assumptions.safe()
    if args.assume is not None:
        return Assumptions.from_names(parse_assumption_names(args.assume))
    return Assumptions.from_names()


def report_assumption_requirements(
    path: pathlib.Path, diagnostics: list[AssumptionDiagnostic]
) -> None:
    """Print skipped conversions that require risky assumptions."""
    for diagnostic in diagnostics:
        assumptions = ",".join(sorted(diagnostic.assumptions))
        print(
            f"Info: {path}:{diagnostic.line}:{diagnostic.column + 1}: "
            f"if/elif chain requires --assume {assumptions}"
        )


def report_result(
    path: pathlib.Path, changed: bool, error: str | None, verbose: bool
) -> tuple[int, int, int]:
    if error:
        print(f"Error processing {path}: {error}")
        return (0, 0, 1)
    if changed:
        print(f"Converted: {path}")
        return (1, 0, 0)
    if verbose:
        print(f"No changes: {path}")
    return (0, 1, 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert if/elif/else chains to Python 3.10+ match statements"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=pathlib.Path,
        help="Python files or directories to process",
    )
    assumption_group = parser.add_mutually_exclusive_group()
    assumption_group.add_argument(
        "--assume",
        metavar="NAMES",
        help=(
            "Comma-separated risky assumptions to enable "
            f"(available: {', '.join(sorted(ALL_RISKY_ASSUMPTIONS))})"
        ),
    )
    assumption_group.add_argument(
        "--safe",
        dest="safe_assumptions",
        action="store_true",
        help="Disable all risky assumptions",
    )
    assumption_group.add_argument(
        "--risky",
        action="store_true",
        help="Enable all risky assumptions",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel jobs (default: number of CPU cores)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show files with no changes"
    )
    parser.add_argument(
        "--no-types",
        type=str,
        default=r".*_TYPES$",
        help="Regex pattern for isinstance type variables to ignore (default: .*_TYPES$)",
    )

    args = parser.parse_args()
    try:
        assumptions = resolve_assumptions(args)
    except ValueError as error:
        parser.error(str(error))

    python_files = collect_python_files(args.paths)

    if not python_files:
        print("No Python files found to process")
        return

    converted_count = 0
    unchanged_count = 0
    error_count = 0

    if len(python_files) == 1:
        result = convert_file(
            python_files[0],
            ignore_types_pattern=args.no_types,
            assumptions=assumptions,
            report_assumption_diagnostics=True,
        )
        converted, unchanged, errors = report_result(*result, verbose=args.verbose)
        converted_count += converted
        unchanged_count += unchanged
        error_count += errors
    else:
        with ProcessPoolExecutor(max_workers=args.jobs or None) as executor:
            convert = partial(
                convert_file,
                ignore_types_pattern=args.no_types,
                assumptions=assumptions,
                report_assumption_diagnostics=True,
            )
            for result in executor.map(convert, python_files):
                converted, unchanged, errors = report_result(
                    *result, verbose=args.verbose
                )
                converted_count += converted
                unchanged_count += unchanged
                error_count += errors

    print(
        f"\nSummary: {converted_count} converted, {unchanged_count} unchanged, {error_count} errors"
    )
