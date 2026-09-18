"""Command-line and file processing helpers."""

import argparse
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import NamedTuple

from .assumptions import (
    ALL_RISKY_ASSUMPTIONS,
    AssumptionDiagnostic,
    Assumptions,
    parse_assumption_names,
)
from .conversion_filter import (
    DEFAULT_CONVERSION_FILTER,
    ConversionFilter,
    ConversionFilterDiagnostic,
    ConversionMetrics,
)
from .diff import print_location_heading, print_preview_metadata, report_diff
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
    report_assumption_diagnostics: bool = False,
    check: bool = False,
    convert_if: str | ConversionFilter | None = None,
    report_filter_diagnostics: bool = False,
) -> tuple[pathlib.Path, bool, str | None]:
    """Convert a single file.

    Returns:
        Tuple of (path, changed, error_message)
    """
    result = _convert_file(
        path,
        ignore_types_pattern,
        assumptions=assumptions,
        report_assumption_diagnostics=report_assumption_diagnostics,
        check=check,
        convert_if=convert_if,
        report_filter_diagnostics=report_filter_diagnostics,
    )
    return result.path, result.changed, result.error


def _convert_file(
    path: pathlib.Path,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    report_assumption_diagnostics: bool = False,
    check: bool = False,
    keep_text: bool = False,
    convert_if: str | ConversionFilter | None = None,
    report_filter_diagnostics: bool = False,
) -> ConvertResult:
    try:
        source = path.read_text(encoding="utf-8")
        diagnostics: list[AssumptionDiagnostic] = []
        filter_diagnostics: list[ConversionFilterDiagnostic] = []
        transformed_code = transform_code(
            source,
            ignore_types_pattern=ignore_types_pattern,
            assumptions=assumptions,
            diagnostics=diagnostics,
            convert_if=convert_if,
            filter_diagnostics=filter_diagnostics,
        )

        if report_assumption_diagnostics:
            report_assumption_requirements(path, diagnostics)
        if report_filter_diagnostics:
            report_filter_rejections(path, filter_diagnostics)
        if transformed_code != source:
            if not check:
                path.write_text(transformed_code, encoding="utf-8")
            text = transformed_code if keep_text else None
            return ConvertResult(path, True, None, text)
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


class PreviewResult(NamedTuple):
    """Collected conversions for one file, or the error that prevented them."""

    path: pathlib.Path
    error: str | None
    previews: list[ChainPreview]
    filter_diagnostics: list[ConversionFilterDiagnostic]


def _preview_file(
    path: pathlib.Path,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    convert_if: str | ConversionFilter | None = None,
) -> PreviewResult:
    try:
        source = path.read_text(encoding="utf-8")
        filter_diagnostics: list[ConversionFilterDiagnostic] = []
        return PreviewResult(
            path,
            None,
            collect_chain_previews(
                source,
                ignore_types_pattern=ignore_types_pattern,
                assumptions=assumptions,
                include_gated=True,
                convert_if=convert_if,
                filter_diagnostics=filter_diagnostics,
            ),
            filter_diagnostics,
        )
    except Exception as error:
        return PreviewResult(path, str(error), [], [])


def _present_preview(
    result: PreviewResult,
    *,
    show_all: bool,
    report_errors: bool,
    report_assumption_diagnostics: bool,
    report_filter_diagnostics: bool,
) -> tuple[int, int, int, int]:
    """Print one file's previews and return hidden, converted, unchanged, errors."""
    if result.error is not None:
        if report_errors:
            _, _, errors = report_result(
                result.path, False, result.error, verbose=False, check=True
            )
            return (0, 0, 0, errors)
        return (0, 0, 0, 0)

    eligible: list[ChainPreview] = []
    gated: dict[frozenset[str], list[ChainPreview]] = {}
    gated_previews: list[ChainPreview] = []
    for preview in result.previews:
        if preview.extra_assumptions:
            gated.setdefault(preview.extra_assumptions, []).append(preview)
            gated_previews.append(preview)
        else:
            eligible.append(preview)

    _emit_previews(result.path, eligible)
    if show_all:
        for required in sorted(gated, key=sorted):
            names = ",".join(sorted(required))
            print(f"\nAdditional conversions require --assume {names}:")
            _emit_previews(result.path, gated[required])
    if report_assumption_diagnostics:
        report_assumption_requirements(
            result.path,
            [
                AssumptionDiagnostic(
                    line=preview.line,
                    column=preview.column,
                    assumptions=preview.extra_assumptions,
                )
                for preview in gated_previews
            ],
        )
    if report_filter_diagnostics:
        report_filter_rejections(result.path, result.filter_diagnostics)
    converted = int(bool(eligible))
    return (len(gated_previews), converted, 1 - converted, 0)


def report_filter_rejections(
    path: pathlib.Path, diagnostics: list[ConversionFilterDiagnostic]
) -> None:
    """Print convertible chains rejected by the stylistic filter."""
    for diagnostic in diagnostics:
        print(
            f"Info: {path}:{diagnostic.line}:{diagnostic.column + 1}: "
            "if/elif chain rejected by --convert-if"
        )


def _map_paths(func, python_files: list[pathlib.Path], jobs: int | None):
    if len(python_files) == 1:
        yield func(python_files[0])
        return
    with ProcessPoolExecutor(max_workers=jobs or None) as executor:
        yield from executor.map(func, python_files)


def _emit_previews(path: pathlib.Path, previews: list[ChainPreview]) -> None:
    for index, preview in enumerate(previews):
        if index:
            print()
        print_location_heading(path, preview.line)
        report_diff(preview.before, preview.after, start_line=preview.line)
        if preview.metrics is not None:
            formatted_metrics = _format_conversion_metrics(preview.metrics)
            if formatted_metrics is not None:
                print_preview_metadata(formatted_metrics)
        print()


def _format_conversion_metrics(metrics: ConversionMetrics) -> str | None:
    values = [
        f"{name}={value}"
        for name in ConversionMetrics.ordered_names()
        if (value := getattr(metrics, name)) != 0
    ]
    if not values:
        return None
    return f"    metrics: {', '.join(values)}"


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
    parser.add_argument(
        "--convert-if",
        metavar="EXPRESSION",
        action="append",
        help=(
            "Convert eligible if/elif chains only when the metrics expression matches "
            f"(default: {DEFAULT_CONVERSION_FILTER})"
        ),
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
    jobs: int | None,
    report_errors: bool,
    report_assumption_diagnostics: bool,
    convert_if: str | ConversionFilter | None = None,
    report_filter_diagnostics: bool = False,
) -> tuple[int, int, int, int]:
    """Show conversions without changing files.

    Each conversion is printed as its own diff under ``<file>:<line>``.
    ``--show-all`` also previews conversions unlocked by the minimal missing
    assumption set.

    Returns hidden, converted, unchanged, and error counts. Hidden counts
    assumption-gated conversions; those diffs are printed only when
    ``show_all`` is true.
    """
    preview = partial(
        _preview_file,
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions,
        convert_if=convert_if,
    )
    hidden_count = converted_count = unchanged_count = error_count = 0
    for result in _map_paths(preview, python_files, jobs):
        hidden, converted, unchanged, errors = _present_preview(
            result,
            show_all=show_all,
            report_errors=report_errors,
            report_assumption_diagnostics=report_assumption_diagnostics,
            report_filter_diagnostics=report_filter_diagnostics,
        )
        hidden_count += hidden
        converted_count += converted
        unchanged_count += unchanged
        error_count += errors
    return hidden_count, converted_count, unchanged_count, error_count


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
    keep_text: bool = False,
    convert_if: str | ConversionFilter | None = None,
    report_filter_diagnostics: bool = False,
) -> tuple[int, int, int, list[ConvertResult]]:
    convert = partial(
        _convert_file,
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions,
        report_assumption_diagnostics=report_assumption_diagnostics,
        check=check,
        keep_text=keep_text,
        convert_if=convert_if,
        report_filter_diagnostics=report_filter_diagnostics,
    )
    converted_count = unchanged_count = error_count = 0
    changed: list[ConvertResult] = []
    for result in _map_paths(convert, python_files, jobs):
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
        if keep_text and result.changed and result.error is None:
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
    if args.convert_if is not None and len(args.convert_if) > 1:
        parser.error("--convert-if may only be specified once")
    try:
        assumptions = resolve_assumptions(args)
        expression = (
            args.convert_if[0]
            if args.convert_if is not None
            else DEFAULT_CONVERSION_FILTER
        )
        conversion_filter = ConversionFilter.parse(expression)
    except ValueError as error:
        parser.error(str(error))
    mode = resolve_cli_mode(args, parser)

    python_files = collect_python_files(args.paths)
    if not python_files:
        print("No Python files found to process")
        return

    apply_changes = mode.write or mode.interactive
    hidden_count = 0
    converted_count = unchanged_count = error_count = 0
    changed: list[ConvertResult] = []
    if mode.showing:
        hidden_count, converted_count, unchanged_count, error_count = preview_files(
            python_files,
            ignore_types_pattern=mode.no_types,
            assumptions=assumptions,
            show_all=mode.show_all,
            jobs=mode.jobs,
            report_errors=not apply_changes,
            report_assumption_diagnostics=not apply_changes and not mode.show_all,
            convert_if=conversion_filter,
            report_filter_diagnostics=mode.verbose,
        )

    if apply_changes:
        converted_count, unchanged_count, error_count, changed = convert_files(
            python_files,
            ignore_types_pattern=mode.no_types,
            assumptions=assumptions,
            jobs=mode.jobs,
            report_assumption_diagnostics=not mode.show_all,
            check=mode.dry_run,
            verbose=mode.verbose,
            quiet=mode.showing,
            keep_text=mode.interactive,
            convert_if=conversion_filter,
            report_filter_diagnostics=mode.verbose,
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
