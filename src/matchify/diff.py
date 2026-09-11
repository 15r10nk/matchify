"""Rich conversion diffs."""

import difflib
import pathlib
import re

from rich.console import Console
from rich.text import Text

console = Console()

WORD_TOKEN_RE = re.compile(r"\s+|\w+|[^\w\s]")
# Dark red/green backgrounds for added/removed tokens.
REMOVED_LINE_STYLE = "on #421b24"
REMOVED_WORD_STYLE = "bold on #792432"
ADDED_LINE_STYLE = "on #183d2c"
ADDED_WORD_STYLE = "bold on #1c6b43"
LINE_NUMBER_STYLE = "dim"
HEADING_PATH_STYLE = "bold bright_cyan"
HEADING_SEPARATOR_STYLE = "bold bright_black"
HEADING_LINE_STYLE = "bold bright_yellow"


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


def print_location_heading(path: pathlib.Path, line: int) -> None:
    text = Text()
    text.append(str(path), style=HEADING_PATH_STYLE)
    text.append(":", style=HEADING_SEPARATOR_STYLE)
    text.append(str(line), style=HEADING_LINE_STYLE)
    console.print(text, soft_wrap=True)


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
