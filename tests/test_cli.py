import pathlib
import sys
import tempfile
from textwrap import dedent

import libcst as cst
import pytest

from matchify.__main__ import (
    IfToMatchTransformer,
    convert_file,
    main,
)


def check_code(source: str, expected: str) -> None:
    """
    Test helper that:
    1. Transforms source code using IfToMatchTransformer
    2. Verifies the transformed code matches expected output
    3. Executes both source and expected code and verifies identical output
    """
    # Transform the source code
    module = cst.parse_module(source)
    wrapper = cst.MetadataWrapper(module)
    transformed = wrapper.visit(IfToMatchTransformer())
    
    # Check transformation matches expected
    assert transformed.code.strip() == expected.strip(), (
        f"Transformation mismatch:\n"
        f"Expected:\n{expected}\n\n"
        f"Got:\n{transformed.code}"
    )
    
    # Execute both code snippets in the same process and capture output
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
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


class TestIfToMatchTransformer:
    """Test the IfToMatchTransformer class."""

    def test_simple_if_elif_else_chain(self):
        """Test conversion of simple if/elif/else chain with == comparisons."""
        source = dedent("""
            x = 5
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            else:
                print("other")
        """).strip()

        expected = dedent("""
            x = 5
            match x:
                case 1:
                    print("one")
                case 2:
                    print("two")
                case _:
                    print("other")
        """).strip()

        check_code(source, expected)

    def test_if_elif_without_else(self):
        """Test conversion of if/elif chain without else clause."""
        source = dedent("""
            status = "active"
            if status == "active":
                print("activate")
            elif status == "inactive":
                print("deactivate")
        """).strip()

        expected = dedent("""
            status = "active"
            match status:
                case "active":
                    print("activate")
                case "inactive":
                    print("deactivate")
        """).strip()

        check_code(source, expected)

    def test_multiple_statements_in_body(self):
        """Test conversion with multiple statements in case bodies."""
        source = dedent("""
            color = "red"
            if color == "red":
                print("Red")
                value = 1
            elif color == "blue":
                print("Blue")
                value = 2
            else:
                print("Unknown")
                value = 0
            print(f"Value: {value}")
        """).strip()

        expected = dedent("""
            color = "red"
            match color:
                case "red":
                    print("Red")
                    value = 1
                case "blue":
                    print("Blue")
                    value = 2
                case _:
                    print("Unknown")
                    value = 0
            print(f"Value: {value}")
        """).strip()

        check_code(source, expected)

    def test_numeric_comparisons(self):
        """Test conversion with numeric literal comparisons."""
        source = dedent("""
            num = 1
            if num == 0:
                print("zero")
            elif num == 1:
                print("one")
            elif num == 2:
                print("two")
        """).strip()

        expected = dedent("""
            num = 1
            match num:
                case 0:
                    print("zero")
                case 1:
                    print("one")
                case 2:
                    print("two")
        """).strip()

        check_code(source, expected)

    def test_non_equality_comparisons_not_converted(self):
        """Test that non-equality comparisons are not transformed."""
        source = dedent("""
            x = 6
            if x > 5:
                print("big")
            elif x < 2:
                print("small")
        """).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_different_variables_not_converted(self):
        """Test that chains comparing different variables are not converted."""
        source = dedent("""
            x = 1
            y = 2
            if x == 1:
                print("x is 1")
            elif y == 2:
                print("y is 2")
        """).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_mixed_operators_not_converted(self):
        """Test that chains with mixed operators are not converted."""
        source = dedent("""
            x = 3
            if x == 1:
                print("one")
            elif x != 2:
                print("not two")
        """).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_nested_if_not_affected(self):
        """Test that nested if statements are handled correctly."""
        source = dedent("""
            x = 1
            y = 2
            if x == 1:
                if y == 2:
                    print("nested")
            elif x == 3:
                print("three")
        """).strip()

        expected = dedent("""
            x = 1
            y = 2
            match x:
                case 1:
                    if y == 2:
                        print("nested")
                case 3:
                    print("three")
        """).strip()

        check_code(source, expected)

    def test_attribute_access_variable(self):
        """Test conversion with attribute access as subject."""
        source = dedent("""
            class Obj:
                status = "ready"
            obj = Obj()
            if obj.status == "ready":
                print("start")
            elif obj.status == "busy":
                print("wait")
        """).strip()

        expected = dedent("""
            class Obj:
                status = "ready"
            obj = Obj()
            match obj.status:
                case "ready":
                    print("start")
                case "busy":
                    print("wait")
        """).strip()

        check_code(source, expected)

    def test_function_call_converted(self):
        """Test that comparisons with function calls ARE converted (they use same function)."""
        source = dedent("""
            def get_value():
                return 1
            if get_value() == 1:
                print("one")
            elif get_value() == 2:
                print("two")
        """).strip()

        expected = dedent("""
            def get_value():
                return 1
            match get_value():
                case 1:
                    print("one")
                case 2:
                    print("two")
        """).strip()

        check_code(source, expected)

    def test_simple_if_only_not_converted(self):
        """Test that single if statement without elif is not converted."""
        source = dedent("""
            x = 1
            if x == 1:
                print("one")
        """).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_multiple_independent_if_chains(self):
        """Test that multiple independent if chains are all converted."""
        source = dedent("""
            x = 1
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            y = "a"
            if y == "a":
                print("a")
            elif y == "b":
                print("b")
        """).strip()

        expected = dedent("""
            x = 1
            match x:
                case 1:
                    print("one")
                case 2:
                    print("two")
            y = "a"
            match y:
                case "a":
                    print("a")
                case "b":
                    print("b")
        """).strip()

        check_code(source, expected)

    def test_comparison_with_variable_not_converted(self):
        """Test that comparisons against variables/constants are NOT converted.
        
        In Python match statements, bare names like 'case WIDTH:' are binding patterns
        that capture any value, NOT comparisons to the variable WIDTH. This would create
        invalid code because binding patterns make subsequent patterns unreachable.
        
        The transformer now correctly detects these cases and does NOT convert them.
        """
        source = dedent("""
            WIDTH = 100
            HEIGHT = 200
            x = 100
            if x == WIDTH:
                print("matches width")
            elif x == HEIGHT:
                print("matches height")
            else:
                print("no match")
        """).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_isinstance_converted(self):
        """Test that isinstance checks are converted to match with class patterns.
        
        isinstance() calls can be converted to match statements using class patterns.
        isinstance(node, Point) becomes case Point().
        """
        source = dedent("""
            class Point:
                pass
            class Line:
                pass
            node = Point()
            if isinstance(node, Point):
                print("point")
            elif isinstance(node, Line):
                print("line")
            else:
                print("other")
        """).strip()

        expected = dedent("""
            class Point:
                pass
            class Line:
                pass
            node = Point()
            match node:
                case Point():
                    print("point")
                case Line():
                    print("line")
                case _:
                    print("other")
        """).strip()
        
        check_code(source, expected)

    def test_isinstance_tuple_converted(self):
        """Test that isinstance with tuple of classes is converted to MatchOr pattern.
        
        isinstance(value, (int, float)) becomes case int() | float().
        """
        source = dedent("""
            value = 42
            if isinstance(value, (int, float)):
                print("number")
            elif isinstance(value, str):
                print("string")
            else:
                print("other")
        """).strip()

        expected = dedent("""
            value = 42
            match value:
                case int() | float():
                    print("number")
                case str():
                    print("string")
                case _:
                    print("other")
        """).strip()
        
        check_code(source, expected)

    def test_is_none_converted(self):
        """Test that 'is None' comparisons are converted to match with None singleton.
        
        'if x is None:' becomes 'case None:' using MatchSingleton pattern.
        """
        source = dedent("""
            x = None
            if x is None:
                print("none")
            elif x == 1:
                print("one")
            elif x == 2:
                print("two")
        """).strip()

        expected = dedent("""
            x = None
            match x:
                case None:
                    print("none")
                case 1:
                    print("one")
                case 2:
                    print("two")
        """).strip()
        
        check_code(source, expected)

    def test_mixed_is_none_and_isinstance(self):
        """Test mixed chain with 'is None' and isinstance checks.
        
        Combines identity comparison (is None) with isinstance checks.
        """
        source = dedent("""
            class Color:
                pass
            value = None
            if value is None:
                print("none")
            elif isinstance(value, Color):
                print("color")
            elif isinstance(value, str):
                print("string")
        """).strip()

        expected = dedent("""
            class Color:
                pass
            value = None
            match value:
                case None:
                    print("none")
                case Color():
                    print("color")
                case str():
                    print("string")
        """).strip()
        
        check_code(source, expected)

    def test_different_subjects_not_converted(self):
        """Test that chains with different subjects are NOT converted.
        
        When if uses isinstance(command, X) but elif uses len(command) == Y,
        the subjects are different (command vs len(command)), so no conversion
        should happen to avoid partial chain conversion.
        """
        source = dedent("""
            class SimpleCommand:
                pass
            command = (1, 2)
            if isinstance(command, SimpleCommand):
                print("simple")
            elif len(command) == 2:
                print("two")
            elif len(command) == 3:
                print("three")
        """).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_isinstance_with_and_converted(self):
        """Test that isinstance with 'and' attribute checks is converted to class pattern with keywords.
        
        Conditions like 'isinstance(node, Point) and node.x == 5' become 'case Point(x=5):'.
        """
        source = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(5, 10)
            if isinstance(node, Point) and node.x == 5:
                print("point at x=5")
            elif isinstance(node, Point):
                print("other point")
        """).strip()

        expected = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(5, 10)
            match node:
                case Point(x=5):
                    print("point at x=5")
                case Point():
                    print("other point")
        """).strip()
        
        check_code(source, expected)

    def test_isinstance_with_multiple_and_converted(self):
        """Test that isinstance with multiple chained 'and' attribute checks works.
        
        Conditions like 'isinstance(node, Point) and node.x == 5 and node.y == 10' 
        become 'case Point(x=5, y=10):'.
        """
        source = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(5, 10)
            if isinstance(node, Point) and node.x == 5 and node.y == 10:
                print("exact point")
            elif isinstance(node, Point):
                print("other point")
        """).strip()

        expected = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(5, 10)
            match node:
                case Point(x=5, y=10):
                    print("exact point")
                case Point():
                    print("other point")
        """).strip()
        
        check_code(source, expected)

    def test_isinstance_with_is_none_attribute(self):
        """Test that isinstance with 'is None' attribute check works.
        
        Conditions like 'isinstance(node, Point) and node.x is None' 
        become 'case Point(x=None):'.
        """
        source = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(None, 10)
            if isinstance(node, Point) and node.x is None:
                print("x is none")
            elif isinstance(node, Point) and node.x == 5:
                print("x is 5")
            else:
                print("other")
        """).strip()

        expected = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(None, 10)
            match node:
                case Point(x=None):
                    print("x is none")
                case Point(x=5):
                    print("x is 5")
                case _:
                    print("other")
        """).strip()
        
        check_code(source, expected)

    def test_isinstance_with_is_true_false(self):
        """Test that isinstance with 'is True/False' attribute checks work.
        
        Conditions like 'isinstance(obj, Config) and obj.enabled is True' 
        become 'case Config(enabled=True):'.
        """
        source = dedent("""
            class Config:
                def __init__(self, enabled):
                    self.enabled = enabled
            obj = Config(True)
            if isinstance(obj, Config) and obj.enabled is True:
                print("enabled")
            elif isinstance(obj, Config) and obj.enabled is False:
                print("disabled")
            else:
                print("other")
        """).strip()

        expected = dedent("""
            class Config:
                def __init__(self, enabled):
                    self.enabled = enabled
            obj = Config(True)
            match obj:
                case Config(enabled=True):
                    print("enabled")
                case Config(enabled=False):
                    print("disabled")
                case _:
                    print("other")
        """).strip()
        
        check_code(source, expected)

    def test_negative_numbers_in_comparisons(self):
        """Test that negative numbers work in comparisons.
        
        Both top-level and attribute checks should support negative numbers.
        """
        source = dedent("""
            x = -5
            if x == -5:
                print("negative five")
            elif x == -10:
                print("negative ten")
            else:
                print("other")
        """).strip()

        expected = dedent("""
            x = -5
            match x:
                case -5:
                    print("negative five")
                case -10:
                    print("negative ten")
                case _:
                    print("other")
        """).strip()
        
        check_code(source, expected)

    def test_negative_numbers_in_attributes(self):
        """Test that negative numbers work in isinstance attribute checks."""
        source = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            p = Point(-5, 10)
            if isinstance(p, Point) and p.x == -5:
                print("x is -5")
            elif isinstance(p, Point) and p.y == 10:
                print("y is 10")
        """).strip()

        expected = dedent("""
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            p = Point(-5, 10)
            match p:
                case Point(x=-5):
                    print("x is -5")
                case Point(y=10):
                    print("y is 10")
        """).strip()
        
        check_code(source, expected)


class TestConvertFile:
    """Test the convert_file function."""

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


class TestMain:
    """Test the main function."""

    def test_main_no_arguments(self, capsys):
        """Test main function with no arguments."""
        import sys
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
        import sys
        
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
                sys.argv = ["matchify", str(test_file)]
                main()
                
                result = test_file.read_text(encoding="utf-8")
                assert "match x:" in result
                
                captured = capsys.readouterr()
                assert "Converted:" in captured.out
            finally:
                sys.argv = original_argv

    def test_main_with_directory(self, capsys):
        """Test main function with a directory."""
        import sys
        
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
        import sys
        
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
                sys.argv = ["matchify", str(test_dir)]
                main()
                
                # Both files should be converted
                assert "match x:" in file1.read_text(encoding="utf-8")
                assert "match x:" in file2.read_text(encoding="utf-8")
            finally:
                sys.argv = original_argv

    def test_main_with_non_python_file(self, capsys):
        """Test main function with a non-Python file."""
        import sys
        
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
        import sys
        
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
                sys.argv = ["matchify", str(file1), str(file2)]
                main()
                
                # Both files should be converted
                assert "match x:" in file1.read_text(encoding="utf-8")
                assert "match x:" in file2.read_text(encoding="utf-8")
                
                captured = capsys.readouterr()
                assert captured.out.count("Converted:") == 2
            finally:
                sys.argv = original_argv


class TestExtractSubject:
    """Test the _extract_subject helper method."""

    def test_extract_subject_from_simple_equality(self):
        """Test extracting subject from simple equality comparison."""
        transformer = IfToMatchTransformer()
        
        source = "x == 1"
        test_expr = cst.parse_expression(source)
        
        subject = transformer._extract_subject(test_expr)
        assert subject is not None
        assert subject.deep_equals(cst.parse_expression("x"))

    def test_extract_subject_from_non_equality(self):
        """Test that non-equality comparisons return None."""
        transformer = IfToMatchTransformer()
        
        source = "x > 5"
        test_expr = cst.parse_expression(source)
        
        subject = transformer._extract_subject(test_expr)
        assert subject is None

    def test_extract_subject_from_complex_expression(self):
        """Test extracting subject from attribute access."""
        transformer = IfToMatchTransformer()
        
        source = "obj.attr == 'value'"
        test_expr = cst.parse_expression(source)
        
        subject = transformer._extract_subject(test_expr)
        assert subject is not None
        assert subject.deep_equals(cst.parse_expression("obj.attr"))
