"""Command-line and file processing helpers."""

import argparse
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import NamedTuple

from libcst import ParserSyntaxError

from .assumptions import (
    ALL_RISKY_ASSUMPTIONS,
    AssumptionDiagnostic,
    Assumptions,
    parse_assumption_names,
)
from .diff import print_location_heading, report_diff
from .transform import ChainPreview, collect_chain_previews, transform_code


class ConvertResult(NamedTuple):
    """Outcome of processing one Python file."""

    path: pathlib.Path
    changed: bool
    error: str | None
    text: str | None = None


class CliMode(NamedTuple):
    """Resolved CLI mode flags."""

    write: bool
    check: bool
    show: bool
    show_all: bool
    interactive: bool
    verbose: bool
    jobs: int | None
    no_types: str

    @property
    def dry_run(self) -> bool:
        return not self.write

    @property
    def showing(self) -> bool:
        return self.show or self.show_all


def convert_file(
    path: pathlib.Path,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    assume_pure_subjects: bool = False,
    report_assumption_diagnostics: bool = False,
    check: bool = False,
) -> tuple[pathlib.Path, bool, str | None]:
    """Convert a single file.

    Returns:
        Tuple of (path, changed, error_message)
    """
    result = _convert_file(
        path,
        ignore_types_pattern,
        assumptions=assumptions,
        assume_pure_subjects=assume_pure_subjects,
        report_assumption_diagnostics=report_assumption_diagnostics,
        check=check,
    )
    return result.path, result.changed, result.error


def _convert_file(
    path: pathlib.Path,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    assume_pure_subjects: bool = False,
    report_assumption_diagnostics: bool = False,
    check: bool = False,
) -> ConvertResult:
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
            if not check:
                path.write_text(transformed_code, encoding="utf-8")
            return ConvertResult(path, True, None, transformed_code)
        return ConvertResult(path, False, None)
    except Exception as e:
        return ConvertResult(path, False, str(e))


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


def report_previews(
    path: pathlib.Path,
    *,
    ignore_types_pattern: str | None,
    assumptions: Assumptions,
    show_all: bool,
) -> int:
    """Show conversions without changing *path*.

    Each conversion is printed as its own diff under ``<file>:<line>``.
    ``--show-all`` also previews conversions unlocked by the minimal missing
    assumption set.

    Returns the number of assumption-gated conversions. Those diffs are printed
    only when ``show_all`` is true.
    """
    source = path.read_text(encoding="utf-8")
    eligible: list[ChainPreview] = []
    gated: dict[frozenset[str], list[ChainPreview]] = {}
    for preview in collect_chain_previews(
        source,
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions,
        include_gated=True,
    ):
        if preview.extra_assumptions:
            gated.setdefault(preview.extra_assumptions, []).append(preview)
        else:
            eligible.append(preview)

    _emit_previews(path, eligible)
    if show_all:
        for required in sorted(gated, key=sorted):
            names = ",".join(sorted(required))
            print(f"\nAdditional conversions require --assume {names}:")
            _emit_previews(path, gated[required])
    return sum(len(group) for group in gated.values())


def _emit_previews(path: pathlib.Path, previews: list[ChainPreview]) -> None:
    for index, preview in enumerate(previews):
        if index:
            print()
        print_location_heading(path, preview.line)
        report_diff(preview.before, preview.after, start_line=preview.line)


def report_hidden_conversions(count: int) -> None:
    """Tell ``--show`` users about gated conversions they can preview."""
    if not count:
        return
    noun = "conversion" if count == 1 else "conversions"
    view = "it" if count == 1 else "them"
    print(
        f"{count} {noun} not shown because of missing --assume. "
        f"View {view} with --show-all."
    )


def report_result(
    path: pathlib.Path,
    changed: bool,
    error: str | None,
    verbose: bool,
    check: bool,
    *,
    quiet: bool = False,
) -> tuple[int, int, int]:
    if error:
        print(f"Error processing {path}: {error}")
        return (0, 0, 1)
    if changed:
        if not quiet:
            action = "Would convert" if check else "Converted"
            print(f"{action}: {path}")
        return (1, 0, 0)
    if verbose and not quiet:
        print(f"No changes: {path}")
    return (0, 1, 0)


def build_parser() -> argparse.ArgumentParser:
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
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--write",
        action="store_true",
        help="Write eligible conversions to files",
    )
    mode_group.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not write files; show diffs and exit with 1 if any file would "
            "change or errors occur"
        ),
    )
    show_group = parser.add_mutually_exclusive_group()
    show_group.add_argument(
        "--show",
        action="store_true",
        help="Show eligible conversions as diffs without failing when files would change",
    )
    show_group.add_argument(
        "--show-all",
        action="store_true",
        help=(
            "Preview eligible and assumption-gated conversions as diffs "
            "before processing files"
        ),
    )
    parser.add_argument(
        "--no-types",
        type=str,
        default=r".*_TYPES$",
        help="Regex pattern for isinstance type variables to ignore (default: .*_TYPES$)",
    )
    return parser


def resolve_cli_mode(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> CliMode:
    show_all = args.show_all
    show = args.show or (args.check and not show_all)
    interactive = not args.write and not args.check and not show and not show_all
    if interactive:
        if not sys.stdin.isatty():
            parser.error(
                "--write, --check, or --show is required in a non-interactive shell"
            )
        show = True
    return CliMode(
        write=args.write,
        check=args.check,
        show=show,
        show_all=show_all,
        interactive=interactive,
        verbose=args.verbose,
        jobs=args.jobs,
        no_types=args.no_types,
    )


def preview_files(
    python_files: list[pathlib.Path],
    *,
    ignore_types_pattern: str | None,
    assumptions: Assumptions,
    show_all: bool,
) -> int:
    hidden_count = 0
    for path in python_files:
        try:
            hidden_count += report_previews(
                path,
                ignore_types_pattern=ignore_types_pattern,
                assumptions=assumptions,
                show_all=show_all,
            )
        except (OSError, UnicodeError, ParserSyntaxError):
            # convert_file reports the processing error in the normal flow.
            pass
    return hidden_count


def convert_files(
    python_files: list[pathlib.Path],
    *,
    ignore_types_pattern: str | None,
    assumptions: Assumptions,
    jobs: int | None,
    report_assumption_diagnostics: bool,
    check: bool,
    verbose: bool,
    quiet: bool,
) -> tuple[int, int, int, list[ConvertResult]]:
    convert = partial(
        _convert_file,
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions,
        report_assumption_diagnostics=report_assumption_diagnostics,
        check=check,
    )
    if len(python_files) == 1:
        results = [convert(python_files[0])]
    else:
        with ProcessPoolExecutor(max_workers=jobs or None) as executor:
            results = list(executor.map(convert, python_files))

    converted_count = unchanged_count = error_count = 0
    changed: list[ConvertResult] = []
    for result in results:
        converted, unchanged, errors = report_result(
            result.path,
            result.changed,
            result.error,
            verbose=verbose,
            check=check,
            quiet=quiet,
        )
        converted_count += converted
        unchanged_count += unchanged
        error_count += errors
        if result.changed and result.error is None:
            changed.append(result)
    return converted_count, unchanged_count, error_count, changed


def confirm_write(changed: list[ConvertResult]) -> None:
    answer = input("Write these changes? [y/N] ")
    if answer.strip().lower() not in {"y", "yes"}:
        return
    write_errors = 0
    for result in changed:
        try:
            result.path.write_text(result.text or "", encoding="utf-8")
        except OSError as error:
            print(f"Error processing {result.path}: {error}")
            write_errors += 1
    if write_errors:
        raise SystemExit(1)
    print(f"Wrote changes to {len(changed)} file(s)")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        assumptions = resolve_assumptions(args)
    except ValueError as error:
        parser.error(str(error))
    mode = resolve_cli_mode(args, parser)

    python_files = collect_python_files(args.paths)
    if not python_files:
        print("No Python files found to process")
        return

    hidden_count = 0
    if mode.showing:
        hidden_count = preview_files(
            python_files,
            ignore_types_pattern=mode.no_types,
            assumptions=assumptions,
            show_all=mode.show_all,
        )

    converted_count, unchanged_count, error_count, changed = convert_files(
        python_files,
        ignore_types_pattern=mode.no_types,
        assumptions=assumptions,
        jobs=mode.jobs,
        report_assumption_diagnostics=not mode.show_all,
        check=mode.dry_run,
        verbose=mode.verbose,
        quiet=mode.showing,
    )

    changed_label = "would convert" if mode.dry_run else "converted"
    print(
        f"\nSummary: {converted_count} {changed_label}, "
        f"{unchanged_count} unchanged, {error_count} errors"
    )
    if mode.show and not mode.show_all:
        report_hidden_conversions(hidden_count)
    if mode.interactive and converted_count and not error_count:
        confirm_write(changed)
    if error_count or (mode.check and converted_count):
        raise SystemExit(1)
