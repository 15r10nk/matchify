import pathlib
import runpy
import sys
import tempfile
from importlib import import_module
from textwrap import dedent

import pytest

from matchify.cli import convert_file, main


class TestConvertFile:
    """Test the convert_file function."""

    def test_convert_file_with_changes(self):
        """Test converting a file that needs changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent(
                """
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """
            ).strip()

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
            source = dedent(
                """
                # No convertible if/elif chains
                if x > 5:
                    print("big")
            """
            ).strip()

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
            source = dedent(
                """
                # Comment with unicode: café
                if status == "☕":
                    print("coffee")
                elif status == "🍵":
                    print("tea")
            """
            ).strip()

            test_file.write_text(source, encoding="utf-8")
            convert_file(test_file)

            result = test_file.read_text(encoding="utf-8")
            assert "café" in result
            assert "☕" in result


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

    def test_main_with_single_file(self, capsys):
        """Test main function with a single Python file."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent(
                """
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """
            ).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", str(test_file)]
                main()

                result = test_file.read_text(encoding="utf-8")
                assert "match x:" in result

                captured = capsys.readouterr()
                assert "Converted:" in captured.out
            finally:
                sys.argv = original_argv

    def test_module_entrypoint_with_single_file(self, capsys):
        """Test running the package module invokes the CLI entry point."""

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "test.py"
            source = dedent(
                """
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """
            ).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["python -m matchify", str(test_file)]
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

            source = dedent(
                """
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """
            ).strip()

            file1.write_text(source, encoding="utf-8")
            file2.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", str(test_dir)]
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

            source = dedent(
                """
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """
            ).strip()

            file1.write_text(source, encoding="utf-8")
            file2.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", str(test_dir)]
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
                sys.argv = ["matchify", str(test_file)]
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

            source = dedent(
                """
                if x == 1:
                    print("one")
                elif x == 2:
                    print("two")
            """
            ).strip()

            file1.write_text(source, encoding="utf-8")
            file2.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", str(file1), str(file2)]
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
            source = dedent(
                """
                if x > 5:
                    print("big")
            """
            ).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", str(test_file)]
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
            source = dedent(
                """
                # No convertible patterns
                if x > 5:
                    print("big")
            """
            ).strip()
            test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--verbose", str(test_file)]
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
                sys.argv = ["matchify", "--jobs", "2", "--verbose", str(test_dir)]
                main()

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
                sys.argv = ["matchify", "--jobs", "2", str(test_dir)]
                main()

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
                sys.argv = ["matchify", "-v", str(test_dir)]
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
                source = dedent(
                    f"""
                    x = {i}
                    if x == 1:
                        print("one")
                    elif x == 2:
                        print("two")
                """
                ).strip()
                test_file.write_text(source, encoding="utf-8")

            original_argv = sys.argv
            try:
                sys.argv = ["matchify", "--jobs", "2", str(test_dir)]
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
                sys.argv = ["matchify", str(test_file)]
                main()

                captured = capsys.readouterr()
                assert "Error processing" in captured.out
                assert "1 errors" in captured.out or "error" in captured.out.lower()
            finally:
                sys.argv = original_argv
