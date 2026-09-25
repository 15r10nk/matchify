import multiprocessing
import os
import pathlib
import runpy
import signal
import subprocess
import sys
import tempfile
import time
from importlib import import_module
from io import StringIO
from textwrap import dedent

import pytest
from rich.console import Console

from matchify.assumptions import Assumptions
from matchify.cli import (
    _emit_previews,
    convert_file,
    convert_files,
    main,
    preview_files,
)
from matchify.conversion_filter import ConversionMetrics
from matchify.diff import print_location_heading, print_preview_metadata, report_diff
from matchify.transform import ChainPreview, collect_chain_previews


class TestConvertFile:
    """Test the convert_file function."""

    def test_report_diff_uses_colored_rich_output(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=True, color_system="truecolor"),
        )

        report_diff("before\n", "after\n", start_line=12)

        rendered = output.getvalue()
        assert "\x1b[" in rendered
        assert "48;2;" in rendered
        assert "12" in rendered
        assert "---" not in rendered
        assert "+++" not in rendered
        assert "@@" not in rendered

    def test_report_diff_ignores_indentation(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=True, color_system="truecolor"),
        )

        report_diff(
            "if enabled:\n    handle()\n",
            "if enabled:\n        handle()\n",
            start_line=1,
        )

        assert output.getvalue() == ""

    def test_report_diff_skips_identical_snippets(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=False, color_system=None),
        )

        report_diff("same\n", "same\n", start_line=1)

        assert output.getvalue() == ""

    def test_report_diff_prints_deleted_and_inserted_lines(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=False, color_system=None),
        )

        report_diff("keep\nremoved\n", "keep\n", start_line=4)
        report_diff("keep\n", "keep\ninserted\n", start_line=8)

        rendered = output.getvalue()
        assert "5 -removed" in rendered
        assert "9 +inserted" in rendered

    def test_report_diff_prints_unpaired_removed_replace_lines(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=False, color_system=None),
        )

        report_diff("alpha\nbeta extra\n", "omega\n", start_line=1)

        rendered = output.getvalue()
        assert "1 -alpha" in rendered
        assert "2 -beta extra" in rendered
        assert "1 +omega" in rendered

    def test_location_heading_uses_color(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=True, color_system="truecolor"),
        )

        print_location_heading(pathlib.Path("demo.py"), 4)

        rendered = output.getvalue()
        assert "demo.py" in rendered
        assert "4" in rendered
        assert "\x1b[" in rendered

    def test_location_heading_does_not_wrap_long_paths(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=False, color_system=None, width=40),
        )
        path = pathlib.Path(
            "/tmp/pytest-of-runner/pytest-0/popen-gw1/test_main_show_prints_one_diff0/test.py"
        )

        print_location_heading(path, 1)

        rendered = output.getvalue()
        assert rendered.splitlines()[0] == f"{path}:1"

    def test_preview_metadata_uses_rich_highlighting_for_numbers(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=True, color_system="truecolor"),
        )

        print_preview_metadata("    metrics: branches=2, patterns=3")

        rendered = output.getvalue()
        assert "branches" in rendered
        assert "patterns" in rendered
        assert "\x1b[" in rendered

    def test_report_diff_prints_ellipsis_between_hunks(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            "matchify.diff.console",
            Console(file=output, force_terminal=False, color_system=None),
        )

        unchanged = "".join(f"same{index}\n" for index in range(20))
        report_diff(
            f"old-start\n{unchanged}old-end\n",
            f"new-start\n{unchanged}new-end\n",
            start_line=10,
        )

        rendered = output.getvalue()
        assert "10 -old-start" in rendered
        assert "10 +new-start" in rendered
        assert "..." in rendered
        assert "@@" not in rendered
        assert "---" not in rendered
        assert "+++" not in rendered

    def test_convert_file_with_changes(self):
        """Test converting a file that needs changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()

            test_file.write_text(source, encoding="utf-8")

            path, changed, error = convert_file(test_file)

            assert path == test_file
            assert changed is True
            assert error is None

            result = test_file.read_text(encoding="utf-8")
            assert "match x:" in result
            assert "case 1:" in result

    def test_convert_file_no_changes(self):
        """Test converting a file that doesn't need changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                # No convertible if/elif chains
                if x > 5:
                    print("big")
            """).strip()

            test_file.write_text(source, encoding="utf-8")
            original_content = test_file.read_text(encoding="utf-8")

            path, changed, error = convert_file(test_file)

            assert path == test_file
            assert changed is False
            assert error is None

            result = test_file.read_text(encoding="utf-8")
            assert result == original_content

    def test_convert_file_preserves_encoding(self):
        """Test that file encoding is preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                # Comment with unicode: café
                if status == "☕":
                    print("coffee")
                elif status == "🍵":
                    print("tea")
            """).strip()

            test_file.write_text(source, encoding="utf-8")
            convert_file(test_file)

            result = test_file.read_text(encoding="utf-8")
            assert "café" in result
            assert "☕" in result

    def test_convert_file_accepts_assumptions(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                if a.x == 1 and b.y == 2:
                    print("first")
                elif a.x == 3 and b.y == 4:
                    print("second")
                """).strip(),
            encoding="utf-8",
        )

        _, changed, error = convert_file(
            test_file,
            assumptions=Assumptions.from_names({"pure-subjects"}),
        )

        assert changed is True
        assert error is None
        assert "match (a.x, b.y):" in test_file.read_text(encoding="utf-8")

    def test_convert_file_check_reports_changes_without_writing(self, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        path, changed, error = convert_file(test_file, check=True)

        assert path == test_file
        assert changed is True
        assert error is None
        assert test_file.read_text(encoding="utf-8") == source

    def test_convert_files_omits_transformed_text_unless_kept(self, tmp_path, capsys):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            "if x == 1:\n    pass\nelif x == 2:\n    pass\n", encoding="utf-8"
        )
        kwargs = dict(
            ignore_types_pattern=None,
            assumptions=Assumptions.from_names(),
            jobs=None,
            report_assumption_diagnostics=False,
            check=True,
            verbose=False,
            quiet=True,
            convert_if="True",
            report_filter_diagnostics=False,
        )

        converted, unchanged, errors, changed = convert_files(
            [test_file], keep_text=False, **kwargs
        )
        assert (converted, unchanged, errors) == (1, 0, 0)
        assert changed == []

        converted, unchanged, errors, kept = convert_files(
            [test_file], keep_text=True, **kwargs
        )
        assert (converted, unchanged, errors) == (1, 0, 0)
        assert len(kept) == 1
        assert kept[0].path == test_file
        assert kept[0].text is not None
        assert "match x:" in kept[0].text
        capsys.readouterr()

    def test_convert_file_accepts_conversion_filter(self, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        _, changed, error = convert_file(test_file, convert_if="branches >= 3")
        assert changed is False
        assert error is None
        assert test_file.read_text(encoding="utf-8") == source
        assert test_file.read_text(encoding="utf-8") == source


class TestMain:
    """Test the main function."""

    def test_module_can_be_imported_without_running_cli(self):
        """Test importing the module entry point does not parse CLI arguments."""

        module = import_module("matchify.__main__")
        assert module.main is main

    def test_main_no_arguments(self, capsys):
        """Test main function with no arguments."""

        original_argv = sys.argv
        try:
            sys.argv = ["matchify"]
            with pytest.raises(SystemExit) as exc_info:
                main()
            # argparse returns exit code 2 for missing required arguments
            assert exc_info.value.code == 2

            captured = capsys.readouterr()
            # argparse writes error messages to stderr
            assert "usage:" in captured.err or "Usage:" in captured.err
        finally:
            sys.argv = original_argv

    def test_main_requires_mode_in_non_interactive_shell(
        self, capsys, tmp_path, monkeypatch
    ):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('x')", encoding="utf-8")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        assert "--write, --check, or --show is required" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--show", "--show-all"])
    def test_main_show_without_write_is_preview_only(
        self, capsys, tmp_path, monkeypatch, flag
    ):
        test_file = tmp_path / "test.py"
        source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
        test_file.write_text(source, encoding="utf-8")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", flag, str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "+match x:" in output
        assert "    metrics: branches=2" in output
        assert "literal_checks=2" in output
        assert "patterns=2" in output
        assert "isinstance_checks=0" not in output
        assert "Wrote changes" not in output
        assert "Would convert:" not in output
        assert "1 would convert" in output

    def test_main_interactively_previews_and_writes_after_confirmation(
        self, capsys, tmp_path, monkeypatch
    ):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            "if x == 1:\n    pass\nelif x == 2:\n    pass\n", encoding="utf-8"
        )
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        prompts: list[str] = []
        monkeypatch.setattr(
            "builtins.input", lambda prompt: prompts.append(prompt) or "yes"
        )

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert "match x:" in test_file.read_text(encoding="utf-8")
        assert prompts == ["Write these changes? [y/N] "]
        output = capsys.readouterr().out
        assert f"{test_file}:1" in output
        assert output.index("4      pass") < output.index("    metrics: branches=2")
        assert "metrics: branches=2" in output
        assert "1 +match x:" in output
        assert "Would convert:" not in output
        assert "Wrote changes to 1 file(s)" in output

    def test_main_interactively_declines_writing(self, capsys, tmp_path, monkeypatch):
        test_file = tmp_path / "test.py"
        source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
        test_file.write_text(source, encoding="utf-8")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda prompt: "n")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "Wrote changes" not in output
        assert "1 would convert" in output

    @pytest.mark.parametrize("flags", [[], ["--write"], ["--show", "--write"]])
    def test_main_write_failure_reports_errors(
        self, capsys, tmp_path, monkeypatch, flags
    ):
        test_file = tmp_path / "test.py"
        source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
        test_file.write_text(source, encoding="utf-8")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda prompt: "yes")

        def fail_write(self, *args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(pathlib.Path, "write_text", fail_write)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", *flags, str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert f"Error processing {test_file}: permission denied" in output
        assert "Wrote changes" not in output
        assert test_file.read_text(encoding="utf-8") == source

    def test_main_interactive_reports_required_assumption(
        self, capsys, tmp_path, monkeypatch
    ):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """).strip()
        test_file.write_text(source, encoding="utf-8")
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert test_file.read_text(encoding="utf-8") == source
        assert (
            f"Info: {test_file}:1:1: if/elif chain requires --assume use-object"
            in output
        )
        assert "Wrote changes" not in output

    def test_main_rejects_write_and_check_together(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('x')", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        assert "not allowed with argument" in capsys.readouterr().err

    def test_main_with_single_file(self, capsys):
        """Test main function with a single Python file."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(test_file)]
                main()

                result = test_file.read_text(encoding="utf-8")
                assert "match x:" in result

                captured = capsys.readouterr()
                assert "Converted:" in captured.out
            finally:
                sys.argv = original_argv

    def test_main_check_with_convertible_file_exits_one_without_writing(
        self, capsys, tmp_path
    ):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert output.index('4      print("two")') < output.index(
            "    metrics: branches=2"
        )
        assert f"{test_file}:1" in output
        assert "metrics: branches=2" in output
        assert "1 +match x:" in output
        assert "Would convert:" not in output
        assert "1 would convert, 0 unchanged, 0 errors" in output

    def test_main_check_with_unchanged_file_exits_zero(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = "print('already fine')"
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "Would convert:" not in output
        assert "0 would convert, 1 unchanged, 0 errors" in output

    def test_main_check_does_not_convert_files(self, capsys, tmp_path, monkeypatch):
        test_file = tmp_path / "test.py"
        source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
        test_file.write_text(source, encoding="utf-8")

        def boom(*args, **kwargs):
            raise AssertionError("check should not transform whole files")

        monkeypatch.setattr("matchify.cli._convert_file", boom)
        monkeypatch.setattr("matchify.cli.convert_files", boom)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "+match x:" in output
        assert "metrics: branches=2" in output
        assert "1 would convert, 0 unchanged, 0 errors" in output

    def test_main_show_does_not_convert_files(self, capsys, tmp_path, monkeypatch):
        test_file = tmp_path / "test.py"
        source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
        test_file.write_text(source, encoding="utf-8")

        def boom(*args, **kwargs):
            raise AssertionError("show should not transform whole files")

        monkeypatch.setattr("matchify.cli._convert_file", boom)
        monkeypatch.setattr("matchify.cli.convert_files", boom)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "+match x:" in output
        assert "1 would convert, 0 unchanged, 0 errors" in output

    def test_main_check_multiple_files_does_not_convert_files(
        self, capsys, tmp_path, monkeypatch
    ):
        test_dir = tmp_path / "src"
        test_dir.mkdir()
        convertible = test_dir / "a.py"
        unchanged = test_dir / "b.py"
        convertible.write_text(
            "if x == 1:\n    pass\nelif x == 2:\n    pass\n", encoding="utf-8"
        )
        unchanged.write_text("print('ok')\n", encoding="utf-8")

        def boom(*args, **kwargs):
            raise AssertionError("check should not transform whole files")

        monkeypatch.setattr("matchify.cli._convert_file", boom)
        monkeypatch.setattr("matchify.cli.convert_files", boom)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--check", "--jobs", "2", str(test_dir)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "+match x:" in output
        assert "1 would convert, 1 unchanged, 0 errors" in output

    def test_main_show_previews_diff_and_converts(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--write", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert "match x:" in test_file.read_text(encoding="utf-8")
        output = capsys.readouterr().out
        assert f"{test_file}:1" in output
        assert "1 -if x == 1:" in output
        assert "metrics: branches=2" in output
        assert "1 +match x:" in output
        assert "Converted:" not in output
        assert "Would convert:" not in output
        assert "---" not in output
        assert "+++" not in output
        assert "@@" not in output

    def test_main_show_keeps_original_indent(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            def f(x):
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "2 -    if x == 1:" in output
        assert "metrics: branches=2" in output
        assert "2 +    match x:" in output
        assert "3 +        case 1:" in output

    def test_main_show_prints_one_diff_per_conversion(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")

            if y == 3:
                print("three")
            elif y == 4:
                print("four")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert f"{test_file}:1" in output
        assert f"{test_file}:6" in output
        assert output.index(f"{test_file}:1") < output.index(f"{test_file}:6")
        assert output.count("metrics: branches=2") == 2
        assert "+match x:" in output
        assert "+match y:" in output

    def test_main_show_with_check_previews_diff_without_writing(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "+match x:" in output
        assert output.index('4      print("two")') < output.index(
            "    metrics: branches=2"
        )
        assert "metrics: branches=2" in output
        assert "Would convert:" not in output
        assert "not shown" not in output

    def test_main_show_all_previews_assumption_gated_conversion(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show-all", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert f"{test_file}:1" in output
        assert "Additional conversions require --assume use-object:" in output
        assert "metrics: branches=2" in output
        assert "1 +match value:" in output
        assert "+++" not in output
        assert "not shown" not in output

    def test_main_show_all_previews_multiple_gated_conversions(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if first.i == 5:
                print("i")
            elif first.j == 6:
                print("j")

            if second.i == 7:
                print("k")
            elif second.j == 8:
                print("l")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show-all", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert f"{test_file}:1" in output
        assert f"{test_file}:6" in output
        assert "Additional conversions require --assume use-object:" in output
        assert output.count("metrics: branches=2") == 2

    def test_main_show_all_keeps_eligible_and_gated_conversions_apart(
        self, capsys, tmp_path
    ):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")

            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show-all", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "1 +match x:" in output
        assert "Additional conversions require --assume use-object:" in output
        assert output.count("metrics: branches=2") == 2
        assert "+match value:" in output

    def test_main_show_skips_ineligible_chains(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x > 1:
                print("big")
            elif x > 2:
                print("bigger")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert "+match" not in output
        assert "0 would convert" in output
        assert "not shown" not in output

    def test_main_show_reports_one_hidden_assumption_gated_conversion(
        self, capsys, tmp_path
    ):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert "+match" not in output
        assert "Additional conversions require" not in output
        assert (
            f"Info: {test_file}:1:1: if/elif chain requires --assume use-object"
            in output
        )
        assert (
            "1 conversion not shown because of missing --assume. "
            "View it with --show-all."
        ) in output
        assert "0 would convert" in output

    def test_main_show_reports_count_of_hidden_gated_conversions(
        self, capsys, tmp_path
    ):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")

            if first.i == 5:
                print("i")
            elif first.j == 6:
                print("j")

            if second.i == 7:
                print("k")
            elif second.j == 8:
                print("l")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "+match x:" in output
        assert "+match first:" not in output
        assert "+match second:" not in output
        assert (
            "2 conversions not shown because of missing --assume. "
            "View them with --show-all."
        ) in output

    def test_main_show_all_skips_chains_that_stay_ineligible(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == {1}:
                print("one")
            elif x == {2}:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show-all", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert "Additional conversions" not in output
        assert "0 would convert" in output

    def test_main_show_with_syntax_error_still_reports_processing(
        self, capsys, tmp_path
    ):
        test_file = tmp_path / "test.py"
        test_file.write_text("if x == :\n    print('broken')", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "Error processing" in output

    def test_main_check_reports_filter_evaluation_errors(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--check",
                "--convert-if",
                "branches / guard_conditions > 1",
                str(test_file),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert f"Error processing {test_file}: division by zero" in output
        assert "Summary: 0 would convert, 0 unchanged, 1 errors" in output

    def test_main_show_write_with_syntax_error_does_not_write(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = "if x == :\n    print('broken')"
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--write", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        assert test_file.read_text(encoding="utf-8") == source
        output = capsys.readouterr().out
        assert "Error processing" in output
        assert "0 converted, 0 unchanged, 1 errors" in output

    def test_main_show_unexpected_preview_error_does_not_write(
        self, tmp_path, monkeypatch
    ):
        test_file = tmp_path / "test.py"
        source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
        test_file.write_text(source, encoding="utf-8")

        def boom(*args, **kwargs):
            raise RuntimeError("preview bug")

        monkeypatch.setattr("matchify.cli._preview_file", boom)

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show", "--write", str(test_file)]
            with pytest.raises(RuntimeError, match="preview bug"):
                main()
        finally:
            sys.argv = original_argv

        assert test_file.read_text(encoding="utf-8") == source

    def test_main_show_write_previews_lookup_conversions(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            result = {"a": 1, "b": 2}[key]

            def method(operation):
                methods = {"create": "POST", "read": "GET"}
                return methods[operation]
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--show",
                "--write",
                "--assume",
                "lookup-equality",
                str(test_file),
            ]
            main()
        finally:
            sys.argv = original_argv

        transformed = test_file.read_text(encoding="utf-8")
        output = capsys.readouterr().out
        assert "match key:" in transformed
        assert "match operation:" in transformed
        assert "+match key:" in output
        assert "+    match operation:" in output

    def test_main_show_all_previews_gated_lookup(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text('result = {"a": 1, "b": 2}[key]\n', encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--show-all", "--check", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert (
            test_file.read_text(encoding="utf-8") == 'result = {"a": 1, "b": 2}[key]\n'
        )
        output = capsys.readouterr().out
        assert "Additional conversions require --assume lookup-equality:" in output
        assert "+match key:" in output

    def test_collect_chain_previews_omits_gated_unless_requested(self):
        source = dedent("""
            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """).strip()

        hidden = collect_chain_previews(
            source,
            assumptions=Assumptions.from_names(),
            include_gated=False,
        )
        shown = collect_chain_previews(
            source,
            assumptions=Assumptions.from_names(),
            include_gated=True,
        )

        assert hidden == []
        assert len(shown) == 1
        assert shown[0].extra_assumptions == frozenset({"use-object"})
        assert shown[0].metrics is not None
        assert shown[0].metrics.branches == 2

    def test_collect_chain_previews_includes_lookups(self):
        source = dedent("""
            result = {"a": 1, "b": 2}[key]

            def method(operation):
                methods = {"create": "POST", "read": "GET"}
                return methods[operation]

            def compact(): return 1

            def other():
                return 1
            """).strip()
        lookup = Assumptions.from_names({"lookup-equality"})

        hidden = collect_chain_previews(
            source,
            assumptions=Assumptions.from_names(),
            include_gated=False,
        )
        shown = collect_chain_previews(
            source,
            assumptions=Assumptions.from_names(),
            include_gated=True,
        )
        enabled = collect_chain_previews(
            source,
            assumptions=lookup,
            include_gated=False,
        )

        assert hidden == []
        assert len(shown) == 2
        assert {preview.extra_assumptions for preview in shown} == {
            frozenset({"lookup-equality"})
        }
        assert len(enabled) == 2
        assert all(not preview.extra_assumptions for preview in enabled)
        assert all(preview.metrics is None for preview in enabled)
        assert any("match key:" in preview.after for preview in enabled)
        assert any("match operation:" in preview.after for preview in enabled)

    def test_main_check_with_error_exits_one(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("if x == :\n    print('broken')", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--check", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "Error processing" in output
        assert "0 would convert, 0 unchanged, 1 errors" in output

    def test_main_with_error_exits_one(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("if x == :\n    print('broken')", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "Error processing" in output
        assert "0 converted, 0 unchanged, 1 errors" in output

    def test_main_rejects_removed_assume_pure_subjects_flag(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('x')", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--assume-pure-subjects",
                str(test_file),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        assert (
            "unrecognized arguments: --assume-pure-subjects" in capsys.readouterr().err
        )

    def test_main_with_assume_list(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                if a.x == 1 and b.y == 2:
                    print("first")
                elif a.x == 3 and b.y == 4:
                    print("second")
                """).strip(),
            encoding="utf-8",
        )

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--write",
                "--assume",
                "pure-subjects",
                str(test_file),
            ]
            main()
        finally:
            sys.argv = original_argv

        assert "match (a.x, b.y):" in test_file.read_text(encoding="utf-8")
        assert "Converted:" in capsys.readouterr().out

    def test_main_with_list_and_tuple_sequence_assumptions(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                if isinstance(value, (list, tuple)) and len(value) == 1 and value[0] == 1:
                    print("one")
                elif value is None:
                    print("none")
                """).strip(),
            encoding="utf-8",
        )

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--write",
                "--assume",
                "list-sequence-pattern,tuple-sequence-pattern",
                str(test_file),
            ]
            main()
        finally:
            sys.argv = original_argv

        transformed = test_file.read_text(encoding="utf-8")
        assert "case 1,:" in transformed
        assert "if isinstance(value, (list, tuple))" not in transformed
        assert "Converted:" in capsys.readouterr().out

    def test_main_reports_required_assumption_for_skipped_chain(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert test_file.read_text(encoding="utf-8") == source
        assert (
            f"Info: {test_file}:1:1: if/elif chain requires --assume use-object"
            in output
        )
        assert "0 converted, 1 unchanged, 0 errors" in output

    def test_main_reports_required_identity_equality_assumption(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if op is Op.ADD:
                print("add")
            elif op is Op.SUBTRACT:
                print("subtract")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert test_file.read_text(encoding="utf-8") == source
        assert (
            f"Info: {test_file}:1:1: if/elif chain requires --assume identity-equality"
            in output
        )
        assert "0 converted, 1 unchanged, 0 errors" in output

    def test_main_reports_required_hashable_subjects_assumption(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if option in {"-h", "--help"}:
                print("help")
            elif option in {"-V", "--version"}:
                print("version")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert test_file.read_text(encoding="utf-8") == source
        assert (
            f"Info: {test_file}:1:1: if/elif chain requires "
            "--assume hashable-subjects" in output
        )
        assert "0 converted, 1 unchanged, 0 errors" in output

    def test_main_does_not_report_enabled_assumption(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                if value.i == 5:
                    print("i")
                elif value.j == 6:
                    print("j")
                """).strip(),
            encoding="utf-8",
        )

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", "--assume", "use-object", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert "requires --assume" not in output
        assert "match value:" in test_file.read_text(encoding="utf-8")

    def test_main_with_risky_enables_all_assumptions(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                if a.x == 1 and b.y == 2:
                    print("first")
                elif a.x == 3 and b.y == 4:
                    print("second")
                """).strip(),
            encoding="utf-8",
        )

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", "--risky", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert "match (a.x, b.y):" in test_file.read_text(encoding="utf-8")
        assert "Converted:" in capsys.readouterr().out

    def test_main_with_safe_disables_risky_assumptions(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            dedent("""
                if a.x == 1 and b.y == 2:
                    print("first")
                elif a.x == 3 and b.y == 4:
                    print("second")
                """).strip(),
            encoding="utf-8",
        )

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", "--safe", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert "if a.x == 1 and b.y == 2:" in test_file.read_text(encoding="utf-8")
        assert "match (a.x, b.y):" not in test_file.read_text(encoding="utf-8")
        assert "requires --assume pure-subjects" in capsys.readouterr().out

    def test_main_rejects_unknown_assumption(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('x')", encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--assume", "unknown", str(test_file)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        assert "Unknown risky assumption: unknown" in capsys.readouterr().err

    def test_main_rejects_invalid_conversion_filter_before_processing(
        self, capsys, tmp_path
    ):
        missing = tmp_path / "missing.py"

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--convert-if", "unknown > 1", str(missing)]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        output = capsys.readouterr()
        assert "Unknown --convert-if variable: unknown" in output.err
        assert "Skipping" not in output.out

    def test_main_rejects_repeated_conversion_filter(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--convert-if",
                "branches > 2",
                "--convert-if",
                "patterns > 2",
                str(test_file),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        assert "--convert-if may only be specified once" in capsys.readouterr().err

    def test_main_default_converts_simple_two_branch_chain(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text(
            'if value == 1:\n    print("one")\nelif value == 2:\n    print("two")',
            encoding="utf-8",
        )

        original_argv = sys.argv
        try:
            sys.argv = ["matchify", "--write", str(test_file)]
            main()
        finally:
            sys.argv = original_argv

        assert "match value:" in test_file.read_text(encoding="utf-8")
        assert "1 converted, 0 unchanged, 0 errors" in capsys.readouterr().out

    def test_main_rejects_duplicate_conversion_filters(self, capsys, tmp_path):
        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--convert-if",
                "True",
                "--convert-if",
                "branches >= 3",
                str(tmp_path / "test.py"),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = original_argv

        assert exc_info.value.code == 2
        assert "--convert-if may only be specified once" in capsys.readouterr().err

    def test_verbose_reports_filter_rejection(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--convert-if",
                "branches >= 3",
                "--verbose",
                "--write",
                str(test_file),
            ]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        assert (
            f"Info: {test_file}:1:1: if/elif chain rejected by --convert-if" in output
        )
        assert f"No changes: {test_file}" in output

    def test_verbose_show_write_reports_filter_rejection_once(self, capsys, tmp_path):
        test_file = tmp_path / "test.py"
        source = dedent("""
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            """).strip()
        test_file.write_text(source, encoding="utf-8")

        original_argv = sys.argv
        try:
            sys.argv = [
                "matchify",
                "--convert-if",
                "branches >= 3",
                "--verbose",
                "--show",
                "--write",
                str(test_file),
            ]
            main()
        finally:
            sys.argv = original_argv

        output = capsys.readouterr().out
        message = f"Info: {test_file}:1:1: if/elif chain rejected by --convert-if"
        assert output.count(message) == 1
        assert test_file.read_text(encoding="utf-8") == source

    def test_module_entrypoint_with_single_file(self, capsys):
        """Test running the package module invokes the CLI entry point."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["python -m matchify", "--write", str(test_file)]
                sys.modules.pop("matchify.__main__", None)
                runpy.run_module("matchify.__main__", run_name="__main__")

                result = test_file.read_text(encoding="utf-8")
                assert "match x:" in result

                captured = capsys.readouterr()
                assert "Converted:" in captured.out
            finally:
                sys.argv = original_argv

    def test_main_with_directory(self, capsys):
        """Test main function with a directory."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)

            # Create multiple Python files
            file1 = test_dir / "file1.py"
            file2 = test_dir / "file2.py"

            source = dedent("""
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()

            file1.write_text(source, encoding="utf-8")
            file2.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(test_dir)]
                main()

                # Both files should be converted
                assert "match x:" in file1.read_text(encoding="utf-8")
                assert "match x:" in file2.read_text(encoding="utf-8")

                captured = capsys.readouterr()
                assert captured.out.count("Converted:") == 2
            finally:
                sys.argv = original_argv

    def test_main_with_nested_directory(self, capsys):
        """Test main function with nested directories."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)
            nested_dir = test_dir / "subdir"
            nested_dir.mkdir()

            file1 = test_dir / "file1.py"
            file2 = nested_dir / "file2.py"

            source = dedent("""
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()

            file1.write_text(source, encoding="utf-8")
            file2.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(test_dir)]
                main()

                # Both files should be converted
                assert "match x:" in file1.read_text(encoding="utf-8")
                assert "match x:" in file2.read_text(encoding="utf-8")
            finally:
                sys.argv = original_argv

    def test_main_with_non_python_file(self, capsys):
        """Test main function with a non-Python file."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.txt"
            test_file.write_text("Not a Python file", encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(test_file)]
                main()

                captured = capsys.readouterr()
                assert "Skipping" in captured.out
            finally:
                sys.argv = original_argv

    def test_main_with_multiple_arguments(self, capsys):
        """Test main function with multiple file arguments."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)

            file1 = test_dir / "file1.py"
            file2 = test_dir / "file2.py"

            source = dedent("""
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """).strip()

            file1.write_text(source, encoding="utf-8")
            file2.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(file1), str(file2)]
                main()

                # Both files should be converted
                assert "match x:" in file1.read_text(encoding="utf-8")
                assert "match x:" in file2.read_text(encoding="utf-8")

                captured = capsys.readouterr()
                assert captured.out.count("Converted:") == 2
            finally:
                sys.argv = original_argv


class TestCliOptionsAndErrors:
    def test_single_unchanged_file_without_verbose_counts_summary(self, capsys):
        """Test unchanged single-file runs stay quiet except for the summary."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                if x > 5:
                    print("big")
            """).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(test_file)]
                main()

                captured = capsys.readouterr()
                assert "No changes:" not in captured.out
                assert "0 converted, 1 unchanged, 0 errors" in captured.out
            finally:
                sys.argv = original_argv

    def test_verbose_flag_with_unchanged_file(self, capsys):
        """Test --verbose flag shows unchanged files."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent("""
                # No convertible patterns
                if x > 5:
                    print("big")
            """).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", "--verbose", str(test_file)]
                main()

                captured = capsys.readouterr()
                assert "No changes:" in captured.out
            finally:
                sys.argv = original_argv

    def test_multiple_files_with_error_and_verbose_unchanged(self, capsys):
        """Test parallel processing reports both errors and verbose unchanged files."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)
            unchanged_file = test_dir / "unchanged.py"
            broken_file = test_dir / "broken.py"

            unchanged_file.write_text("if x > 5:\n    print('big')", encoding="utf-8")
            broken_file.write_text("if x == :\n    print('broken')", encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = [
                    "matchify",
                    "--write",
                    "--jobs",
                    "2",
                    "--verbose",
                    str(test_dir),
                ]
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "No changes:" in captured.out
                assert "Error processing" in captured.out
                assert "0 converted, 1 unchanged, 1 errors" in captured.out
            finally:
                sys.argv = original_argv

    def test_multiple_files_with_error_and_nonverbose_unchanged(self, capsys):
        """Test parallel processing counts quiet unchanged files."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)
            unchanged_file = test_dir / "unchanged.py"
            broken_file = test_dir / "broken.py"

            unchanged_file.write_text("if x > 5:\n    print('big')", encoding="utf-8")
            broken_file.write_text("if x == :\n    print('broken')", encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", "--jobs", "2", str(test_dir)]
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "No changes:" not in captured.out
                assert "Error processing" in captured.out
                assert "0 converted, 1 unchanged, 1 errors" in captured.out
            finally:
                sys.argv = original_argv

    def test_verbose_flag_with_directory(self, capsys):
        """Test --verbose flag with directory of unchanged files."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)
            test_file = test_dir / "test.py"
            source = "# No patterns\nprint('hello')"
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", "-v", str(test_dir)]
                main()

                captured = capsys.readouterr()
                assert "No changes:" in captured.out
            finally:
                sys.argv = original_argv

    def test_jobs_argument(self, capsys):
        """Test --jobs argument for parallel processing."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = pathlib.Path(tmpdir)

            # Create multiple files
            for i in range(3):
                test_file = test_dir / f"test{i}.py"
                source = dedent(f"""
                    x = {i}
                    if x == 1:
                        print("one")
                    elif x == 2:
                        print("two")
                """).strip()
                test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", "--jobs", "2", str(test_dir)]
                main()

                captured = capsys.readouterr()
                assert "Converted:" in captured.out or "No changes:" in captured.out
            finally:
                sys.argv = original_argv

    def test_convert_file_with_syntax_error(self):
        """Test converting a file with syntax errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = "if x == :\n    print('broken')"
            test_file.write_text(source, encoding="utf-8")

            path, changed, error = convert_file(test_file)

            assert path == test_file
            assert changed is False
            assert error is not None
            assert "Syntax Error" in error or "ParserSyntaxError" in error

    def test_main_with_error_file(self, capsys):
        """Test main function with a file that causes errors."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = "if x == :\n    print('broken')"
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--write", str(test_file)]
                with pytest.raises(SystemExit) as exc_info:
                    main()

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "Error processing" in captured.out
                assert "1 errors" in captured.out or "error" in captured.out.lower()
            finally:
                sys.argv = original_argv


def test_preview_files_can_suppress_parse_errors(tmp_path, capsys):
    path = tmp_path / "broken.py"
    source = "if x == :\n    pass\n"
    path.write_text(source, encoding="utf-8")

    result = preview_files(
        [path],
        ignore_types_pattern=None,
        assumptions=Assumptions.safe(),
        show_all=False,
        jobs=1,
        report_errors=False,
        report_assumption_diagnostics=False,
    )

    assert result == (0, 0, 0, 0, [])
    assert capsys.readouterr().out == ""
    assert path.read_text(encoding="utf-8") == source


def test_preview_omits_empty_metrics(tmp_path, capsys):
    preview = ChainPreview(
        line=1,
        column=0,
        before="before\n",
        after="after\n",
        extra_assumptions=frozenset(),
        metrics=ConversionMetrics(),
    )

    _emit_previews(tmp_path / "example.py", [preview])

    output = capsys.readouterr().out
    assert "before" in output
    assert "after" in output
    assert "metrics:" not in output


@pytest.mark.parametrize("stage", ["collect_python_files", "confirm_write"])
def test_main_handles_keyboard_interrupt(stage, monkeypatch, capsys, tmp_path):
    source = tmp_path / "input.py"
    source.write_text("if x == 1:\n    pass\nelif x == 2:\n    pass\n")
    monkeypatch.setattr(sys, "argv", ["matchify", str(source)])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(f"matchify.cli.{stage}", interrupt)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 130
    assert capsys.readouterr().err == "Interrupted.\n"


@pytest.mark.skipif(
    sys.platform == "win32", reason="Requires POSIX process-group signals"
)
@pytest.mark.parametrize("start_method", multiprocessing.get_all_start_methods())
@pytest.mark.parametrize("file_count", [1, 2])
def test_ctrl_c_stops_cli_and_workers(tmp_path, start_method, file_count):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for index in range(file_count):
        (inputs / f"{index}.py").write_text("pass\n")
    script = tmp_path / "interrupt_cli.py"
    script.write_text(dedent("""\
        import multiprocessing
        import os
        import signal
        import sys
        import time
        import matchify.cli as cli

        def slow_preview(path, **kwargs):
            path.with_suffix(".ready").write_text("ready")
            time.sleep(60)

        original_terminate = cli._stop_workers

        def interrupt_during_cleanup(workers, **kwargs):
            os.killpg(os.getpgrp(), signal.SIGINT)
            os.killpg(os.getpgrp(), signal.SIGINT)
            original_terminate(workers, **kwargs)

        cli._stop_workers = interrupt_during_cleanup
        cli._preview_file = slow_preview
        if __name__ == "__main__":
            multiprocessing.set_start_method(sys.argv.pop(1))
            previous = signal.getsignal(signal.SIGINT)
            try:
                cli.main()
            finally:
                assert signal.getsignal(signal.SIGINT) == previous
                assert not multiprocessing.active_children()
        """))
    _interrupt_cli_process(
        [str(script), start_method, "--show", "--jobs", "2", str(inputs)],
        lambda: len(list(inputs.glob("*.ready"))) == file_count,
    )


@pytest.mark.parametrize(
    ("option", "reporter"),
    [("--show", "_present_preview"), ("--write", "report_result")],
)
def test_interrupt_while_reporting_cleans_up_workers(
    tmp_path, monkeypatch, capsys, option, reporter
):
    for index in range(2):
        (tmp_path / f"{index}.py").write_text("pass\n")
    monkeypatch.setattr(sys, "argv", ["matchify", option, "--jobs", "2", str(tmp_path)])

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(f"matchify.cli.{reporter}", interrupt)
    previous = signal.getsignal(signal.SIGINT)
    children = multiprocessing.active_children()
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 130
    assert signal.getsignal(signal.SIGINT) == previous
    assert multiprocessing.active_children() == children
    assert capsys.readouterr().err == "Interrupted.\n"


@pytest.mark.skipif(
    sys.platform == "win32", reason="Requires POSIX process-group signals"
)
def test_ctrl_c_with_large_results_in_flight(tmp_path):
    script = tmp_path / "busy_results.py"
    ready = tmp_path / "ready"
    script.write_text(dedent("""\
        import multiprocessing
        import pathlib
        import sys
        import time
        from contextlib import closing
        import matchify.cli as cli

        def large_result(index):
            return b"x" * 1_000_000

        def consume():
            with closing(cli._map_paths(large_result, list(range(100)), 24)) as results:
                next(results)
                pathlib.Path(sys.argv[1]).touch()
                time.sleep(60)

        if __name__ == "__main__":
            cli._main = consume
            try:
                cli.main()
            finally:
                assert not multiprocessing.active_children()
        """))
    _interrupt_cli_process([str(script), str(ready)], ready.exists)


def _interrupt_cli_process(arguments, ready):
    process = subprocess.Popen(
        [sys.executable, *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 20
        while not ready():
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline, "Workers did not start"
            time.sleep(0.01)
        os.killpg(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130, (stdout, stderr)
        assert stderr == "Interrupted.\n"
        assert "Summary:" not in stdout
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()


def test_parallel_worker_error_reaches_caller(tmp_path):
    from matchify.cli import _map_paths

    existing = tmp_path / "existing.py"
    existing.write_text("pass\n")
    missing = tmp_path / "missing.py"
    with pytest.raises(FileNotFoundError):
        list(_map_paths(pathlib.Path.read_text, [existing, missing], jobs=2))


@pytest.mark.parametrize(
    ("write", "keep_text"), [(False, False), (True, False), (False, True)]
)
def test_preview_workers_only_render_text_when_needed(
    tmp_path, monkeypatch, capsys, write, keep_text
):
    import matchify.cli as cli

    source = dedent("""\
        if value == 1:
            first()
        elif value == 2:
            second()
        """)
    paths = [tmp_path / f"{index}.py" for index in range(2)]
    for path in paths:
        path.write_text(source)
    returned = []
    original_map = cli._map_paths

    def record_results(*args):
        results = list(original_map(*args))
        returned.extend(results)
        yield from results

    monkeypatch.setattr(cli, "_map_paths", record_results)
    hidden, converted, unchanged, errors, changed = preview_files(
        paths,
        ignore_types_pattern=None,
        assumptions=Assumptions.safe(),
        show_all=False,
        jobs=2,
        report_errors=True,
        report_assumption_diagnostics=True,
        write=write,
        keep_text=keep_text,
    )

    assert (hidden, converted, unchanged, errors) == (0, 2, 0, 0)
    assert len(returned) == 2
    assert all((result.text is not None) == (write or keep_text) for result in returned)
    assert "match value:" in capsys.readouterr().out
    for path in paths:
        if write:
            assert "match value:" in path.read_text()
        else:
            assert path.read_text() == source
    if keep_text:
        assert len(changed) == 2
        assert all("match value:" in result.text for result in changed)
    else:
        assert changed == []


def test_preview_does_not_render_unchanged_files(tmp_path, monkeypatch):
    from matchify.cli import _preview_file

    path = tmp_path / "unchanged.py"
    path.write_text("value = 1\n")

    def unexpected_apply(self):
        pytest.fail("Unchanged files should not be rendered")

    monkeypatch.setattr(
        "matchify.transform.SelectedConversions.apply", unexpected_apply
    )
    result = _preview_file(path, render_text=True)
    assert result.error is None
    assert result.previews == []
    assert result.text is None


def test_interactive_render_failure_does_not_prompt_or_write(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "input.py"
    source = "if x == 1:\n    pass\nelif x == 2:\n    pass\n"
    path.write_text(source)
    monkeypatch.setattr(sys, "argv", ["matchify", str(path)])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def fail_render(self):
        raise RuntimeError("render failed")

    def unexpected_prompt(prompt):
        pytest.fail("Must not prompt after a render failure")

    monkeypatch.setattr("matchify.transform.SelectedConversions.apply", fail_render)
    monkeypatch.setattr("builtins.input", unexpected_prompt)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert path.read_text() == source
    output = capsys.readouterr().out
    assert "render failed" in output
    assert "0 would convert, 0 unchanged, 1 errors" in output


def _work_waiting_for_later_file(path):
    marker = path.parent / "later-file-started"
    match path.name:
        case "0.py":
            deadline = time.monotonic() + 5
            while not marker.exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("Idle worker did not pick up the next file")
                time.sleep(0.01)
        case "2.py":
            marker.touch()
    return path.name


def test_parallel_workers_pick_up_available_work(tmp_path):
    from matchify.cli import _map_paths

    paths = [tmp_path / f"{index}.py" for index in range(3)]
    assert set(_map_paths(_work_waiting_for_later_file, paths, jobs=2)) == {
        path.name for path in paths
    }


@pytest.mark.skipif(
    sys.platform == "win32", reason="Requires POSIX process-group signals"
)
def test_ctrl_c_during_spawn_bootstrap(tmp_path):
    script = tmp_path / "bootstrap.py"
    script.write_text(dedent("""\
        import os
        import pathlib
        import sys
        import time

        if __name__ == "__mp_main__":
            pathlib.Path(sys.argv[1], str(os.getpid()) + ".ready").touch()
            time.sleep(60)

        import multiprocessing
        from contextlib import closing
        import matchify.cli as cli

        def consume():
            with closing(cli._map_paths(str, [1, 2], 2)) as results:
                list(results)

        if __name__ == "__main__":
            multiprocessing.set_start_method("spawn")
            cli._main = consume
            try:
                cli.main()
            finally:
                assert not multiprocessing.active_children()
        """))
    _interrupt_cli_process(
        [str(script), str(tmp_path)],
        lambda: len(list(tmp_path.glob("*.ready"))) == 2,
    )


def test_path_worker_protocol_and_connection_cleanup():
    from matchify.cli import _path_worker

    parent, child = multiprocessing.Pipe()
    inherited, unused = multiprocessing.Pipe()
    previous = signal.getsignal(signal.SIGINT)
    try:
        parent.send("12")
        parent.send("invalid")
        parent.send(None)
        _path_worker(child, int, [inherited])
        assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
        assert parent.recv() == (True, 12)
        success, error = parent.recv()
        assert success is False
        assert isinstance(error, ValueError)
        assert child.closed
        assert inherited.closed
    finally:
        signal.signal(signal.SIGINT, previous)
        parent.close()
        child.close()
        inherited.close()
        unused.close()


@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_atomic_write_failure_preserves_source(tmp_path, monkeypatch, error_type):
    from matchify.cli import _write_source

    path = tmp_path / "source.py"
    path.write_text("original\n")
    original_write = pathlib.Path.write_text

    def partial_write(self, text, **kwargs):
        original_write(self, text[:2], **kwargs)
        raise error_type("interrupted write")

    monkeypatch.setattr(pathlib.Path, "write_text", partial_write)
    with pytest.raises(error_type):
        _write_source(path, "replacement\n")
    assert path.read_text() == "original\n"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes and symlinks")
def test_atomic_write_preserves_mode_and_symlink(tmp_path):
    from matchify.cli import _write_source

    target = tmp_path / "source.py"
    target.write_text("original\n")
    target.chmod(0o751)
    link = tmp_path / "link.py"
    link.symlink_to(target)
    _write_source(link, "replacement\n")
    assert link.is_symlink()
    assert target.read_text() == "replacement\n"
    assert target.stat().st_mode & 0o777 == 0o751


@pytest.mark.skipif(
    sys.platform == "win32", reason="Requires POSIX process-group signals"
)
def test_ctrl_c_during_write_preserves_source(tmp_path):
    source = "if value == 1:\n    first()\nelif value == 2:\n    second()\n"
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for index in range(2):
        (inputs / f"{index}.py").write_text(source)
    ready = tmp_path / "ready"
    script = tmp_path / "interrupt_write.py"
    script.write_text(dedent("""\
        import pathlib
        import sys
        import time
        import matchify.cli as cli

        def slow_write(self, text, **kwargs):
            with self.open("w", **kwargs) as stream:
                stream.write(text[:2])
                stream.flush()
                (pathlib.Path(sys.argv[-1]).parent / "ready").touch()
                time.sleep(60)
                return stream.write(text[2:])

        pathlib.Path.write_text = slow_write
        if __name__ == "__main__":
            cli.main()
        """))
    _interrupt_cli_process(
        [str(script), "--write", "--jobs", "1", str(inputs)], ready.exists
    )
    assert all(path.read_text() == source for path in inputs.glob("*.py"))
