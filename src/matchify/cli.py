"""Command-line and file processing helpers."""

import argparse
import difflib
import pathlib
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import partial

from rich.console import Console
from rich.text import Text

from .assumptions import (
    ALL_RISKY_ASSUMPTIONS,
    AssumptionDiagnostic,
    Assumptions,
    parse_assumption_names,
)
from .transform import collect_chain_previews, transform_code

console = Console()

WORD_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")
# Mirrors textual-diff-view's $error/$success backgrounds: 10% for a changed
# line and 30% for the more prominent inline change.
REMOVED_LINE_STYLE = "on #421b24"
REMOVED_WORD_STYLE = "bold on #792432"
ADDED_LINE_STYLE = "on #183d2c"
ADDED_WORD_STYLE = "bold on #1c6b43"
LINE_NUMBER_STYLE = "dim"
HEADING_PATH_STYLE = "bold bright_cyan"
HEADING_SEPARATOR_STYLE = "bold bright_black"
HEADING_LINE_STYLE = "bold bright_yellow"


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


def report_diff(before: str, after: str, *, start_line: int = 1) -> None:
    """Print a conversion diff without unified-diff headers."""
    if before == after:
        return
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(
        None,
        [line.lstrip() for line in before_lines],
        [line.lstrip() for line in after_lines],
    )
    groups = list(matcher.get_grouped_opcodes())
    if not groups:
        return

    width = len(str(start_line + max(len(before_lines), len(after_lines), 1) - 1))
    for group_index, group in enumerate(groups):
        if group_index:
            _print_diff_control_line("...\n", style="dim")
        for tag, old_start, old_end, new_start, new_end in group:
            if tag == "equal":
                for offset, line in enumerate(before_lines[old_start:old_end]):
                    _print_equal_line(start_line + old_start + offset, width, line)
            elif tag == "delete":
                for offset, line in enumerate(before_lines[old_start:old_end]):
                    _print_word_line(
                        "-",
                        line,
                        REMOVED_LINE_STYLE,
                        REMOVED_WORD_STYLE,
                        line_no=start_line + old_start + offset,
                        width=width,
                    )
            elif tag == "insert":
                for offset, line in enumerate(after_lines[new_start:new_end]):
                    _print_word_line(
                        "+",
                        line,
                        ADDED_LINE_STYLE,
                        ADDED_WORD_STYLE,
                        line_no=start_line + new_start + offset,
                        width=width,
                    )
            else:
                _print_replaced_lines(
                    before_lines[old_start:old_end],
                    after_lines[new_start:new_end],
                    old_start_line=start_line + old_start,
                    new_start_line=start_line + new_start,
                    width=width,
                )


def _print_location_heading(path: pathlib.Path, line: int) -> None:
    text = Text()
    text.append(str(path), style=HEADING_PATH_STYLE)
    text.append(":", style=HEADING_SEPARATOR_STYLE)
    text.append(str(line), style=HEADING_LINE_STYLE)
    console.print(text)


def _print_diff_control_line(line: str, style: str | None = "bold cyan") -> None:
    console.print(
        line,
        end="",
        style=style,
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def _print_equal_line(line_no: int, width: int, line: str) -> None:
    text = _line_number_text(line_no, width)
    text.append(f" {line}")
    console.print(text, end="", highlight=False, soft_wrap=True)


def _line_number_text(line_no: int, width: int) -> Text:
    return Text(f"{line_no:>{width}} ", style=LINE_NUMBER_STYLE)


def _print_replaced_lines(
    old_lines: list[str],
    new_lines: list[str],
    *,
    old_start_line: int,
    new_start_line: int,
    width: int,
) -> None:
    paired_count = min(len(old_lines), len(new_lines))
    for offset, (old_line, new_line) in enumerate(
        zip(old_lines[:paired_count], new_lines[:paired_count])
    ):
        old_tokens = WORD_TOKEN_RE.findall(old_line.lstrip())
        new_tokens = WORD_TOKEN_RE.findall(new_line.lstrip())
        token_matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens)
        old_changed = _changed_token_indexes(token_matcher.get_opcodes(), old=True)
        new_changed = _changed_token_indexes(token_matcher.get_opcodes(), old=False)
        _print_word_line(
            "-",
            old_line,
            REMOVED_LINE_STYLE,
            REMOVED_WORD_STYLE,
            old_changed,
            line_no=old_start_line + offset,
            width=width,
        )
        _print_word_line(
            "+",
            new_line,
            ADDED_LINE_STYLE,
            ADDED_WORD_STYLE,
            new_changed,
            line_no=new_start_line + offset,
            width=width,
        )
    for offset, line in enumerate(old_lines[paired_count:]):
        _print_word_line(
            "-",
            line,
            REMOVED_LINE_STYLE,
            REMOVED_WORD_STYLE,
            line_no=old_start_line + paired_count + offset,
            width=width,
        )
    for offset, line in enumerate(new_lines[paired_count:]):
        _print_word_line(
            "+",
            line,
            ADDED_LINE_STYLE,
            ADDED_WORD_STYLE,
            line_no=new_start_line + paired_count + offset,
            width=width,
        )


def _changed_token_indexes(
    opcodes: list[tuple[str, int, int, int, int]], *, old: bool
) -> set[int]:
    indexes: set[int] = set()
    for tag, old_start, old_end, new_start, new_end in opcodes:
        if tag != "equal":
            start, end = (old_start, old_end) if old else (new_start, new_end)
            indexes.update(range(start, end))
    return indexes


def _print_word_line(
    prefix: str,
    line: str,
    line_style: str,
    changed_style: str,
    changed_tokens: set[int] | None = None,
    *,
    line_no: int,
    width: int,
) -> None:
    indentation_length = len(line) - len(line.lstrip())
    indentation = line[:indentation_length]
    tokens = WORD_TOKEN_RE.findall(line[indentation_length:])
    text = _line_number_text(line_no, width)
    text.append(prefix, style=line_style)
    text.append(indentation, style=line_style)
    for index, token in enumerate(tokens):
        style = (
            changed_style
            if changed_tokens is None or index in changed_tokens
            else line_style
        )
        text.append(token, style=style)
    console.print(text, end="", soft_wrap=True)


def report_previews(
    path: pathlib.Path,
    *,
    ignore_types_pattern: str | None,
    assumptions: Assumptions,
    show_all: bool,
) -> None:
    """Show conversions without changing *path*.

    Each if/elif conversion is printed as its own diff under ``<file>:<line>``.
    ``--show-all`` also previews conversions unlocked by the minimal missing
    assumption set.
    """
    source = path.read_text(encoding="utf-8")
    previews = collect_chain_previews(
        source,
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions,
        include_gated=show_all,
    )
    first = True
    for preview in previews:
        if preview.extra_assumptions:
            continue
        if not first:
            print()
        first = False
        _print_location_heading(path, preview.line)
        report_diff(
            preview.before,
            preview.after,
            start_line=preview.line,
        )

    if not show_all:
        return

    gated = [preview for preview in previews if preview.extra_assumptions]
    for required in sorted({item.extra_assumptions for item in gated}, key=sorted):
        names = ",".join(sorted(required))
        print(f"\nAdditional conversions require --assume {names}:")
        first_gated = True
        for preview in gated:
            if preview.extra_assumptions != required:
                continue
            if not first_gated:
                print()
            first_gated = False
            _print_location_heading(path, preview.line)
            report_diff(
                preview.before,
                preview.after,
                start_line=preview.line,
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
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--write",
        action="store_true",
        help="Write eligible conversions to files",
    )
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Do not write files; exit with 1 if any file would change or errors occur",
    )
    show_group = parser.add_mutually_exclusive_group()
    show_group.add_argument(
        "--show",
        action="store_true",
        help="Show eligible conversions as diffs",
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

    args = parser.parse_args()
    try:
        assumptions = resolve_assumptions(args)
    except ValueError as error:
        parser.error(str(error))

    interactive = not args.write and not args.check
    if interactive and not sys.stdin.isatty():
        parser.error("--write or --check is required in a non-interactive shell")
    if interactive:
        args.show = True

    python_files = collect_python_files(args.paths)

    if not python_files:
        print("No Python files found to process")
        return

    converted_count = 0
    unchanged_count = 0
    error_count = 0
    changed_paths: list[pathlib.Path] = []
    dry_run = args.check or interactive
    showing = args.show or args.show_all

    if args.show or args.show_all:
        for path in python_files:
            try:
                report_previews(
                    path,
                    ignore_types_pattern=args.no_types,
                    assumptions=assumptions,
                    show_all=args.show_all,
                )
            except Exception:
                # convert_file reports the processing error in the normal flow.
                pass

    if len(python_files) == 1:
        result = convert_file(
            python_files[0],
            ignore_types_pattern=args.no_types,
            assumptions=assumptions,
            report_assumption_diagnostics=not args.show,
            check=dry_run,
        )
        converted, unchanged, errors = report_result(
            *result, verbose=args.verbose, check=dry_run, quiet=showing
        )
        converted_count += converted
        unchanged_count += unchanged
        error_count += errors
        if result[1] and result[2] is None:
            changed_paths.append(result[0])
    else:
        with ProcessPoolExecutor(max_workers=args.jobs or None) as executor:
            convert = partial(
                convert_file,
                ignore_types_pattern=args.no_types,
                assumptions=assumptions,
                report_assumption_diagnostics=not args.show,
                check=dry_run,
            )
            for result in executor.map(convert, python_files):
                converted, unchanged, errors = report_result(
                    *result, verbose=args.verbose, check=dry_run, quiet=showing
                )
                converted_count += converted
                unchanged_count += unchanged
                error_count += errors
                if result[1] and result[2] is None:
                    changed_paths.append(result[0])

    changed_label = "would convert" if dry_run else "converted"
    print(
        f"\nSummary: {converted_count} {changed_label}, "
        f"{unchanged_count} unchanged, {error_count} errors"
    )
    if interactive and converted_count and not error_count:
        answer = input("Write these changes? [y/N] ")
        if answer.strip().lower() in {"y", "yes"}:
            for path in changed_paths:
                convert_file(
                    path,
                    ignore_types_pattern=args.no_types,
                    assumptions=assumptions,
                )
            print(f"Wrote changes to {len(changed_paths)} file(s)")

    if error_count or (args.check and converted_count):
        raise SystemExit(1)
