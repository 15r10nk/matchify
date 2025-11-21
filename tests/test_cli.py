import pathlib
import sys
import tempfile
from textwrap import dedent

import libcst as cst
import pytest

from matchify.__main__ import (
    IfToMatchTransformer,
    CapturePatternTransformer,
    convert_file,
    main,
)


def check_code(source: str, expected: str, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
    """
    Test helper that:
    1. Transforms source code using IfToMatchTransformer
    2. Applies CapturePatternTransformer (second pass)
    3. Verifies the transformed code matches expected output
    4. Executes both source and expected code and verifies identical output
    """
    # Transform the source code
    module = cst.parse_module(source)
    wrapper = cst.MetadataWrapper(module)
    transformed = wrapper.visit(IfToMatchTransformer(ignore_types_pattern=ignore_types_pattern))
    
    # Second pass: add capture patterns
    transformed = transformed.visit(CapturePatternTransformer())

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
        source = dedent(
            """
            x = 5
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            x = 5
            match x:
                case 1:
                    print("one")
                case 2:
                    print("two")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_if_elif_without_else(self):
        """Test conversion of if/elif chain without else clause."""
        source = dedent(
            """
            status = "active"
            if status == "active":
                print("activate")
            elif status == "inactive":
                print("deactivate")
        """
        ).strip()

        expected = dedent(
            """
            status = "active"
            match status:
                case "active":
                    print("activate")
                case "inactive":
                    print("deactivate")
        """
        ).strip()

        check_code(source, expected)

    def test_multiple_statements_in_body(self):
        """Test conversion with multiple statements in case bodies."""
        source = dedent(
            """
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
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_numeric_comparisons(self):
        """Test conversion with numeric literal comparisons."""
        source = dedent(
            """
            num = 1
            if num == 0:
                print("zero")
            elif num == 1:
                print("one")
            elif num == 2:
                print("two")
        """
        ).strip()

        expected = dedent(
            """
            num = 1
            match num:
                case 0:
                    print("zero")
                case 1:
                    print("one")
                case 2:
                    print("two")
        """
        ).strip()

        check_code(source, expected)

    def test_non_equality_comparisons_not_converted(self):
        """Test that non-equality comparisons are not transformed."""
        source = dedent(
            """
            x = 6
            if x > 5:
                print("big")
            elif x < 2:
                print("small")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_different_variables_not_converted(self):
        """Test that chains comparing different variables are not converted."""
        source = dedent(
            """
            x = 1
            y = 2
            if x == 1:
                print("x is 1")
            elif y == 2:
                print("y is 2")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_mixed_operators_not_converted(self):
        """Test that chains with mixed operators are not converted."""
        source = dedent(
            """
            x = 3
            if x == 1:
                print("one")
            elif x != 2:
                print("not two")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_nested_if_not_affected(self):
        """Test that nested if statements are converted recursively.
        
        Previously, nested if-statements inside match case bodies were not converted.
        Now they are recursively transformed.
        """
        source = dedent(
            """
            x = 1
            y = 2
            if x == 1:
                if y == 2:
                    print("nested")
                elif y == 3:
                    print("three")
            elif x == 3:
                print("outer three")
        """
        ).strip()

        expected = dedent(
            """
            x = 1
            y = 2
            match x:
                case 1:
                    match y:
                        case 2:
                            print("nested")
                        case 3:
                            print("three")
                case 3:
                    print("outer three")
        """
        ).strip()

        check_code(source, expected)

    def test_attribute_access_variable(self):
        """Test conversion with attribute access as subject."""
        source = dedent(
            """
            class Obj:
                status = "ready"
            obj = Obj()
            if obj.status == "ready":
                print("start")
            elif obj.status == "busy":
                print("wait")
        """
        ).strip()

        expected = dedent(
            """
            class Obj:
                status = "ready"
            obj = Obj()
            match obj.status:
                case "ready":
                    print("start")
                case "busy":
                    print("wait")
        """
        ).strip()

        check_code(source, expected)

    def test_function_call_converted(self):
        """Test that comparisons with function calls ARE converted (they use same function)."""
        source = dedent(
            """
            def get_value():
                return 1
            if get_value() == 1:
                print("one")
            elif get_value() == 2:
                print("two")
        """
        ).strip()

        expected = dedent(
            """
            def get_value():
                return 1
            match get_value():
                case 1:
                    print("one")
                case 2:
                    print("two")
        """
        ).strip()

        check_code(source, expected)

    def test_simple_if_only_not_converted(self):
        """Test that single if statement without elif is not converted."""
        source = dedent(
            """
            x = 1
            if x == 1:
                print("one")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_multiple_independent_if_chains(self):
        """Test that multiple independent if chains are all converted."""
        source = dedent(
            """
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
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_comparison_with_variable_not_converted(self):
        """Test that comparisons against variables/constants are NOT converted.

        In Python match statements, bare names like 'case WIDTH:' are binding patterns
        that capture any value, NOT comparisons to the variable WIDTH. This would create
        invalid code because binding patterns make subsequent patterns unreachable.

        The transformer now correctly detects these cases and does NOT convert them.
        """
        source = dedent(
            """
            WIDTH = 100
            HEIGHT = 200
            x = 100
            if x == WIDTH:
                print("matches width")
            elif x == HEIGHT:
                print("matches height")
            else:
                print("no match")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_convertible_chain_after_non_convertible_chain(self):
        """Test that a convertible if-chain following a non-convertible one is still converted.
        
        This is a regression test: previously, if a non-convertible chain failed to convert,
        it left _current_subject set, which prevented subsequent independent chains from converting.
        """
        source = dedent(
            """
            # This chain should NOT be converted (attribute compared to variable, not literal)
            if isinstance(override, CallableType) and override.min_args == original.min_args:
                pass
            elif isinstance(override, Overloaded):
                pass
            
            # This chain SHOULD be converted (independent, valid pattern)
            for ttype in test_types:
                if isinstance(ttype, FunctionLike):
                    pass
                elif isinstance(ttype, TypeType):
                    exc_type = ttype.item
                else:
                    pass
        """
        ).strip()

        expected = dedent(
            """
            # This chain should NOT be converted (attribute compared to variable, not literal)
            if isinstance(override, CallableType) and override.min_args == original.min_args:
                pass
            elif isinstance(override, Overloaded):
                pass
            
            # This chain SHOULD be converted (independent, valid pattern)
            for ttype in test_types:
                match ttype:
                    case FunctionLike():
                        pass
                    case TypeType():
                        exc_type = ttype.item
                    case _:
                        pass
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_converted(self):
        """Test that isinstance checks are converted to match with class patterns.

        isinstance() calls can be converted to match statements using class patterns.
        isinstance(node, Point) becomes case Point().
        """
        source = dedent(
            """
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
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_tuple_converted(self):
        """Test that isinstance with tuple of classes is converted to MatchOr pattern.

        isinstance(value, (int, float)) becomes case int() | float().
        """
        source = dedent(
            """
            value = 42
            if isinstance(value, (int, float)):
                print("number")
            elif isinstance(value, str):
                print("string")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            value = 42
            match value:
                case int() | float():
                    print("number")
                case str():
                    print("string")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_is_none_converted(self):
        """Test that 'is None' comparisons are converted to match with None singleton.

        'if x is None:' becomes 'case None:' using MatchSingleton pattern.
        """
        source = dedent(
            """
            x = None
            if x is None:
                print("none")
            elif x == 1:
                print("one")
            elif x == 2:
                print("two")
        """
        ).strip()

        expected = dedent(
            """
            x = None
            match x:
                case None:
                    print("none")
                case 1:
                    print("one")
                case 2:
                    print("two")
        """
        ).strip()

        check_code(source, expected)

    def test_mixed_is_none_and_isinstance(self):
        """Test mixed chain with 'is None' and isinstance checks.

        Combines identity comparison (is None) with isinstance checks.
        """
        source = dedent(
            """
            class Color:
                pass
            value = None
            if value is None:
                print("none")
            elif isinstance(value, Color):
                print("color")
            elif isinstance(value, str):
                print("string")
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_different_subjects_not_converted(self):
        """Test that chains with different subjects are NOT converted.

        When if uses isinstance(command, X) but elif uses len(command) == Y,
        the bare len() checks without index checks are not converted (to avoid
        incorrect semantics for dicts and other non-sequence types).
        """
        source = dedent(
            """
            class SimpleCommand:
                pass
            command = (1, 2)
            if isinstance(command, SimpleCommand):
                print("simple")
            elif len(command) == 2:
                print("two")
            elif len(command) == 3:
                print("three")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_isinstance_with_and_converted(self):
        """Test that isinstance with 'and' attribute checks is converted to class pattern with keywords.

        Conditions like 'isinstance(node, Point) and node.x == 5' become 'case Point(x=5):'.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(5, 10)
            if isinstance(node, Point) and node.x == 5:
                print("point at x=5")
            elif isinstance(node, Point):
                print("other point")
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_multiple_and_converted(self):
        """Test that isinstance with multiple chained 'and' attribute checks works.

        Conditions like 'isinstance(node, Point) and node.x == 5 and node.y == 10'
        become 'case Point(x=5, y=10):'.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            node = Point(5, 10)
            if isinstance(node, Point) and node.x == 5 and node.y == 10:
                print("exact point")
            elif isinstance(node, Point):
                print("other point")
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_is_none_attribute(self):
        """Test that isinstance with 'is None' attribute check works.

        Conditions like 'isinstance(node, Point) and node.x is None'
        become 'case Point(x=None):'.
        """
        source = dedent(
            """
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
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_is_true_false(self):
        """Test that isinstance with 'is True/False' attribute checks work.

        Conditions like 'isinstance(obj, Config) and obj.enabled is True'
        become 'case Config(enabled=True):'.
        """
        source = dedent(
            """
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
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_negative_numbers_in_comparisons(self):
        """Test that negative numbers work in comparisons.

        Both top-level and attribute checks should support negative numbers.
        """
        source = dedent(
            """
            x = -5
            if x == -5:
                print("negative five")
            elif x == -10:
                print("negative ten")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            x = -5
            match x:
                case -5:
                    print("negative five")
                case -10:
                    print("negative ten")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_negative_numbers_in_attributes(self):
        """Test that negative numbers work in isinstance attribute checks."""
        source = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            p = Point(-5, 10)
            if isinstance(p, Point) and p.x == -5:
                print("x is -5")
            elif isinstance(p, Point) and p.y == 10:
                print("y is 10")
        """
        ).strip()

        expected = dedent(
            """
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
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_simple(self):
        """Test that sequence patterns with subscript checks are converted.

        Patterns like 'len(x) == 2 and x[0] == 0 and x[1] == 1' become 'case [0, 1]:'.
        """
        source = dedent(
            """
            point = (0, 1)
            if len(point) == 2 and point[0] == 0 and point[1] == 1:
                print("origin offset")
            elif len(point) == 2 and point[0] == 1 and point[1] == 1:
                print("diagonal")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            point = (0, 1)
            match point:
                case 0, 1:
                    print("origin offset")
                case 1, 1:
                    print("diagonal")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_three_elements(self):
        """Test sequence patterns with three elements."""
        source = dedent(
            """
            rgb = (255, 0, 0)
            if len(rgb) == 3 and rgb[0] == 255 and rgb[1] == 0 and rgb[2] == 0:
                print("red")
            elif len(rgb) == 3 and rgb[0] == 0 and rgb[1] == 255 and rgb[2] == 0:
                print("green")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            rgb = (255, 0, 0)
            match rgb:
                case 255, 0, 0:
                    print("red")
                case 0, 255, 0:
                    print("green")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_with_strings(self):
        """Test sequence patterns with string literals."""
        source = dedent(
            """
            cmd = ["get", "item"]
            if len(cmd) == 2 and cmd[0] == "get" and cmd[1] == "item":
                print("get item")
            elif len(cmd) == 2 and cmd[0] == "drop" and cmd[1] == "item":
                print("drop item")
        """
        ).strip()

        expected = dedent(
            """
            cmd = ["get", "item"]
            match cmd:
                case "get", "item":
                    print("get item")
                case "drop", "item":
                    print("drop item")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_missing_index_not_converted(self):
        """Test that incomplete sequence patterns are not converted.

        If we check len() == 3 but only check indices 0 and 1, don't convert.
        """
        source = dedent(
            """
            point = (1, 2, 3)
            if len(point) == 3 and point[0] == 1 and point[1] == 2:
                print("incomplete")
            elif len(point) == 3:
                print("complete")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_sequence_pattern_without_len_not_converted(self):
        """Test that subscript checks without len() are not converted."""
        source = dedent(
            """
            point = (1, 2)
            if point[0] == 1 and point[1] == 2:
                print("no len check")
            elif point[0] == 0:
                print("other")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_sequence_pattern_with_isinstance_element(self):
        """Test sequence pattern with isinstance check on an element.

        Tests nested pattern support: isinstance(x[i], Class) inside sequence patterns.
        """
        source = dedent(
            """
            class Point:
                pass
            x = [Point(), 2]
            if len(x) == 2 and isinstance(x[0], Point) and x[1] == 2:
                print("point and 2")
            elif len(x) == 2 and x[0] == 1 and x[1] == 1:
                print("1 and 1")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            x = [Point(), 2]
            match x:
                case Point(), 2:
                    print("point and 2")
                case 1, 1:
                    print("1 and 1")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_with_mixed_isinstance_and_literals(self):
        """Test sequence pattern mixing isinstance and literal checks.

        Tests multiple isinstance elements in a sequence pattern.
        """
        source = dedent(
            """
            class Point:
                pass
            class Color:
                pass
            x = [Point(), Color(), 1]
            if len(x) == 3 and isinstance(x[0], Point) and isinstance(x[1], Color) and x[2] == 1:
                print("point, color, 1")
            elif len(x) == 3 and x[0] == 0 and x[1] == 0 and x[2] == 0:
                print("zeros")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            class Color:
                pass
            x = [Point(), Color(), 1]
            match x:
                case Point(), Color(), 1:
                    print("point, color, 1")
                case 0, 0, 0:
                    print("zeros")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_with_isinstance_and_is_none(self):
        """Test sequence pattern with isinstance and 'is None' checks.

        Tests combining isinstance and identity patterns in sequences.
        """
        source = dedent(
            """
            class Point:
                pass
            x = [Point(), None]
            if len(x) == 2 and isinstance(x[0], Point) and x[1] is None:
                print("point and none")
            elif len(x) == 2 and x[0] == 1 and x[1] == 2:
                print("1 and 2")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            x = [Point(), None]
            match x:
                case Point(), None:
                    print("point and none")
                case 1, 2:
                    print("1 and 2")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_with_isinstance_tuple(self):
        """Test sequence pattern with isinstance tuple (multiple types) on element.

        Tests: isinstance(x[i], (Class1, Class2)) inside sequence patterns.
        Should convert to: case Class1() | Class2(), ...:
        """
        source = dedent(
            """
            class Point:
                pass
            class Line:
                pass
            x = [Point(), 1]
            if len(x) == 2 and isinstance(x[0], (Point, Line)) and x[1] == 1:
                print("point or line and 1")
            elif len(x) == 2 and x[0] == 0 and x[1] == 0:
                print("0 and 0")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            class Line:
                pass
            x = [Point(), 1]
            match x:
                case Point() | Line(), 1:
                    print("point or line and 1")
                case 0, 0:
                    print("0 and 0")
        """
        ).strip()

        check_code(source, expected)

    def test_multiple_sibling_attributes_with_literals(self):
        """Test class with multiple sibling attributes at same level.

        Tests: isinstance(x, Point) with x.a == val1 and x.b == val2 and x.c == val3
        Demonstrates that any number of attributes at the same level work without limits.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z
            p = Point(1, 2, 3)
            if isinstance(p, Point) and p.x == 1 and p.y == 2 and p.z == 3:
                print("exact point")
            elif isinstance(p, Point):
                print("other point")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x, y, z):
                    self.x = x
                    self.y = y
                    self.z = z
            p = Point(1, 2, 3)
            match p:
                case Point(x=1, y=2, z=3):
                    print("exact point")
                case Point():
                    print("other point")
        """
        ).strip()

        check_code(source, expected)

    def test_many_sibling_attributes_no_limit(self):
        """Test class with many attributes to verify no arbitrary limit.

        Tests that 10 attributes at the same level work fine.
        """
        source = dedent(
            """
            class Data:
                def __init__(self, a, b, c, d, e, f, g, h, i, j):
                    self.a = a
                    self.b = b
                    self.c = c
                    self.d = d
                    self.e = e
                    self.f = f
                    self.g = g
                    self.h = h
                    self.i = i
                    self.j = j
            x = Data(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
            if isinstance(x, Data) and x.a == 1 and x.b == 2 and x.c == 3 and x.d == 4 and x.e == 5 and x.f == 6 and x.g == 7 and x.h == 8 and x.i == 9 and x.j == 10:
                print("all ten")
            elif isinstance(x, Data):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Data:
                def __init__(self, a, b, c, d, e, f, g, h, i, j):
                    self.a = a
                    self.b = b
                    self.c = c
                    self.d = d
                    self.e = e
                    self.f = f
                    self.g = g
                    self.h = h
                    self.i = i
                    self.j = j
            x = Data(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
            match x:
                case Data(a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8, i=9, j=10):
                    print("all ten")
                case Data():
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_many_elements_no_limit(self):
        """Test sequence patterns with many elements to verify no limit.

        Tests that 8-element sequences work fine (literals and isinstance mixed).
        """
        source = dedent(
            """
            class A:
                pass
            class B:
                pass
            x = [1, A(), 3, B(), 5, 6, 7, 8]
            if len(x) == 8 and x[0] == 1 and isinstance(x[1], A) and x[2] == 3 and isinstance(x[3], B) and x[4] == 5 and x[5] == 6 and x[6] == 7 and x[7] == 8:
                print("eight elements")
            elif x == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            class A:
                pass
            class B:
                pass
            x = [1, A(), 3, B(), 5, 6, 7, 8]
            match x:
                case 1, A(), 3, B(), 5, 6, 7, 8:
                    print("eight elements")
                case 0:
                    print("zero")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_with_star(self):
        """Test that star patterns work with >= operator.
        
        Patterns like 'len(x) >= 2 and x[0] == 1 and x[1] == 2' become 'case [1, 2, *_]:'.
        """
        source = dedent(
            """
            data = [1, 2, 3, 4, 5]
            if len(data) >= 2 and data[0] == 1 and data[1] == 2:
                print("starts with 1, 2")
            elif len(data) >= 1 and data[0] == 0:
                print("starts with 0")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            data = [1, 2, 3, 4, 5]
            match data:
                case 1, 2, *_:
                    print("starts with 1, 2")
                case 0, *_:
                    print("starts with 0")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_star_with_isinstance(self):
        """Test star patterns with isinstance elements."""
        source = dedent(
            """
            class Point:
                pass
            data = [Point(), 1, 2, 3]
            if len(data) >= 2 and isinstance(data[0], Point) and data[1] == 1:
                print("point then 1")
            elif len(data) >= 1 and isinstance(data[0], Point):
                print("starts with point")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            data = [Point(), 1, 2, 3]
            match data:
                case Point(), 1, *_:
                    print("point then 1")
                case Point(), *_:
                    print("starts with point")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_simple(self):
        """Test basic wildcard pattern with single gap.
        
        Patterns like 'len(x) == 3 and x[0] == 1 and x[2] == 3' become 'case [1, _, 3]:'.
        """
        source = dedent(
            """
            data = [1, "middle", 3]
            if len(data) == 3 and data[0] == 1 and data[2] == 3:
                print("1 and 3 with middle gap")
            elif len(data) == 3 and data[0] == 0 and data[2] == 2:
                print("0 and 2 with middle gap")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            data = [1, "middle", 3]
            match data:
                case 1, _, 3:
                    print("1 and 3 with middle gap")
                case 0, _, 2:
                    print("0 and 2 with middle gap")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_two_consecutive(self):
        """Test wildcard pattern with two consecutive gaps (maximum allowed)."""
        source = dedent(
            """
            data = [1, "a", "b", 4]
            if len(data) == 4 and data[0] == 1 and data[3] == 4:
                print("1 and 4 with two gaps")
            elif len(data) == 4 and data[0] == 0 and data[3] == 3:
                print("0 and 3 with two gaps")
        """
        ).strip()

        expected = dedent(
            """
            data = [1, "a", "b", 4]
            match data:
                case 1, _, _, 4:
                    print("1 and 4 with two gaps")
                case 0, _, _, 3:
                    print("0 and 3 with two gaps")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_three_consecutive_not_converted(self):
        """Test that three consecutive wildcards prevent conversion."""
        source = dedent(
            """
            data = [1, "a", "b", "c", 5]
            if len(data) == 5 and data[0] == 1 and data[4] == 5:
                print("1 and 5 with three gaps")
            elif len(data) == 5 and data[0] == 0 and data[4] == 4:
                print("0 and 4 with three gaps")
        """
        ).strip()

        # Should NOT be converted (3 consecutive wildcards)
        check_code(source, source)

    def test_wildcard_pattern_multiple_groups(self):
        """Test wildcard pattern with multiple separate wildcard groups."""
        source = dedent(
            """
            data = [1, "a", 2, "b", "c", 5]
            if len(data) == 6 and data[0] == 1 and data[2] == 2 and data[5] == 5:
                print("1, 2, 5 with gaps")
            elif len(data) == 6 and data[0] == 0 and data[2] == 1 and data[5] == 3:
                print("0, 1, 3 with gaps")
        """
        ).strip()

        expected = dedent(
            """
            data = [1, "a", 2, "b", "c", 5]
            match data:
                case 1, _, 2, _, _, 5:
                    print("1, 2, 5 with gaps")
                case 0, _, 1, _, _, 3:
                    print("0, 1, 3 with gaps")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_with_isinstance(self):
        """Test wildcard patterns mixed with isinstance checks."""
        source = dedent(
            """
            class Point:
                pass
            data = [Point(), "a", 3]
            if len(data) == 3 and isinstance(data[0], Point) and data[2] == 3:
                print("point and 3 with gap")
            elif len(data) == 3 and isinstance(data[0], Point) and data[2] == 5:
                print("point and 5 with gap")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            data = [Point(), "a", 3]
            match data:
                case Point(), _, 3:
                    print("point and 3 with gap")
                case Point(), _, 5:
                    print("point and 5 with gap")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_at_start(self):
        """Test wildcard at the beginning of a sequence."""
        source = dedent(
            """
            data = ["a", 1, 2]
            if len(data) == 3 and data[1] == 1 and data[2] == 2:
                print("gap then 1, 2")
            elif len(data) == 3 and data[1] == 0 and data[2] == 1:
                print("gap then 0, 1")
        """
        ).strip()

        expected = dedent(
            """
            data = ["a", 1, 2]
            match data:
                case _, 1, 2:
                    print("gap then 1, 2")
                case _, 0, 1:
                    print("gap then 0, 1")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_at_end(self):
        """Test wildcard at the end of a sequence."""
        source = dedent(
            """
            data = [1, 2, "trailing"]
            if len(data) == 3 and data[0] == 1 and data[1] == 2:
                print("1, 2 then gap")
            elif len(data) == 3 and data[0] == 0 and data[1] == 1:
                print("0, 1 then gap")
        """
        ).strip()

        expected = dedent(
            """
            data = [1, 2, "trailing"]
            match data:
                case 1, 2, _:
                    print("1, 2 then gap")
                case 0, 1, _:
                    print("0, 1 then gap")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_with_is_none(self):
        """Test wildcard patterns mixed with is None checks."""
        source = dedent(
            """
            data = [None, "a", 3]
            if len(data) == 3 and data[0] is None and data[2] == 3:
                print("none and 3 with gap")
            elif len(data) == 3 and data[0] is None and data[2] == 5:
                print("none and 5 with gap")
        """
        ).strip()

        expected = dedent(
            """
            data = [None, "a", 3]
            match data:
                case None, _, 3:
                    print("none and 3 with gap")
                case None, _, 5:
                    print("none and 5 with gap")
        """
        ).strip()

        check_code(source, expected)

    def test_wildcard_pattern_not_used_for_mixed(self):
        """Test that wildcard patterns work when some indices are checked."""
        source = dedent(
            """
            data = [1, "middle", 3]
            if len(data) == 3 and data[0] == 1 and data[2] == 3:
                print(f"1 and 3 with {data[1]} in middle")
            elif len(data) == 3 and data[0] == 0 and data[2] == 2:
                print(f"0 and 2 with {data[1]} in middle")
        """
        ).strip()

        expected = dedent(
            """
            data = [1, "middle", 3]
            match data:
                case 1, _, 3:
                    print(f"1 and 3 with {data[1]} in middle")
                case 0, _, 2:
                    print(f"0 and 2 with {data[1]} in middle")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_simple(self):
        """Test basic OR pattern with two values."""
        source = dedent(
            """
            x = 1
            if x == 1 or x == 2:
                print("one or two")
            elif x == 3 or x == 4:
                print("three or four")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            x = 1
            match x:
                case 1 | 2:
                    print("one or two")
                case 3 | 4:
                    print("three or four")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_three_values(self):
        """Test OR pattern with three values."""
        source = dedent(
            """
            color = "red"
            if color == "red" or color == "green" or color == "blue":
                print("primary color")
            elif color == "yellow" or color == "cyan" or color == "magenta":
                print("secondary color")
        """
        ).strip()

        expected = dedent(
            """
            color = "red"
            match color:
                case "red" | "green" | "blue":
                    print("primary color")
                case "yellow" | "cyan" | "magenta":
                    print("secondary color")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_with_strings(self):
        """Test OR pattern with string literals."""
        source = dedent(
            '''
            status = "ready"
            if status == "ready" or status == "running":
                print("active")
            elif status == "stopped" or status == "error":
                print("inactive")
        '''
        ).strip()

        expected = dedent(
            '''
            status = "ready"
            match status:
                case "ready" | "running":
                    print("active")
                case "stopped" | "error":
                    print("inactive")
        '''
        ).strip()

        check_code(source, expected)

    def test_or_pattern_mixed_types(self):
        """Test OR pattern with mixed number types."""
        source = dedent(
            """
            value = 1
            if value == 1 or value == 2.5:
                print("small")
            elif value == 10 or value == 20.0:
                print("large")
        """
        ).strip()

        expected = dedent(
            """
            value = 1
            match value:
                case 1 | 2.5:
                    print("small")
                case 10 | 20.0:
                    print("large")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_with_is_none(self):
        """Test OR pattern with 'is None'."""
        source = dedent(
            """
            value = None
            if value is None or value is False:
                print("falsy singleton")
            elif value is True:
                print("truthy singleton")
        """
        ).strip()

        expected = dedent(
            """
            value = None
            match value:
                case None | False:
                    print("falsy singleton")
                case True:
                    print("truthy singleton")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_with_negative_numbers(self):
        """Test OR pattern with negative numbers."""
        source = dedent(
            """
            temp = -5
            if temp == -5 or temp == -10:
                print("very cold")
            elif temp == 0 or temp == 5:
                print("cold")
        """
        ).strip()

        expected = dedent(
            """
            temp = -5
            match temp:
                case -5 | -10:
                    print("very cold")
                case 0 | 5:
                    print("cold")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_in_mixed_chain(self):
        """Test OR pattern mixed with other pattern types in a chain."""
        source = dedent(
            """
            class Point:
                pass
            value = 1
            if value == 1 or value == 2:
                print("one or two")
            elif isinstance(value, Point):
                print("point")
            elif value is None:
                print("none")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            value = 1
            match value:
                case 1 | 2:
                    print("one or two")
                case Point():
                    print("point")
                case None:
                    print("none")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_or_pattern_with_variable_not_converted(self):
        """Test that OR patterns with variables (non-literals) are not converted."""
        source = dedent(
            """
            x = 1
            y = 2
            if x == 1 or x == y:
                print("match")
            elif x == 3:
                print("three")
        """
        ).strip()

        # Should NOT be converted (y is a variable, not a literal)
        check_code(source, source)

    def test_or_pattern_different_subjects_not_converted(self):
        """Test that OR patterns comparing different subjects are not converted."""
        source = dedent(
            """
            x = 1
            y = 2
            if x == 1 or y == 2:
                print("match")
            elif x == 3:
                print("three")
        """
        ).strip()

        # Should NOT be converted (different subjects)
        check_code(source, source)

    def test_capture_pattern_from_assignment(self):
        """Test capture pattern with assignment-based variable binding.
        
        When first statement is 'var = obj.attr[0]' and pattern has len(obj.attr) >= N,
        convert to use capture: case Class(attr=[var, *_]):
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3])
            if isinstance(n, Point) and len(n.x) >= 1:
                value = n.x[0]
                print(value)
            elif isinstance(n, Point):
                print("empty")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3])
            match n:
                case Point(x=[value, *_]):
                    print(value)
                case Point():
                    print("empty")
        """
        ).strip()

        check_code(source, expected)

    def test_capture_pattern_multiple_values(self):
        """Test multiple capture pattern with consecutive assignments.
        
        When first statements are 'a = obj.attr[0]', 'b = obj.attr[1]', etc.,
        convert to use multiple captures: case Class(attr=[a, b, *_]):
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3])
            if isinstance(n, Point) and len(n.x) >= 2:
                first = n.x[0]
                second = n.x[1]
                print(first, second)
            elif isinstance(n, Point):
                print("empty")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3])
            match n:
                case Point(x=[first, second, *_]):
                    print(first, second)
                case Point():
                    print("empty")
        """
        ).strip()

        check_code(source, expected)

    def test_capture_pattern_three_values(self):
        """Test three capture pattern with consecutive assignments."""
        source = dedent(
            """
            class Data:
                def __init__(self, values):
                    self.values = values

            d = Data([10, 20, 30])
            if isinstance(d, Data) and len(d.values) >= 3:
                a = d.values[0]
                b = d.values[1]
                c = d.values[2]
                print(a, b, c)
            elif isinstance(d, Data):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Data:
                def __init__(self, values):
                    self.values = values

            d = Data([10, 20, 30])
            match d:
                case Data(values=[a, b, c, *_]):
                    print(a, b, c)
                case Data():
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_capture_pattern_non_consecutive_indices(self):
        """Test that non-consecutive indices are converted with wildcards.
        
        If assignments skip indices (e.g., [0] then [2]), captures are created
        with wildcards for skipped indices.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3, 4])
            if isinstance(n, Point) and len(n.x) >= 4:
                first = n.x[0]
                third = n.x[2]
                print(first, third)
            elif isinstance(n, Point):
                print("empty")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3, 4])
            match n:
                case Point(x=[first, _, third, *_]):
                    print(first, third)
                case Point():
                    print("empty")
        """
        ).strip()
        
        check_code(source, expected)

    def test_capture_pattern_multi_attribute(self):
        """Test capturing from multiple different attributes.
        
        Captures from both x and y attributes should work.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y

            n = Point([1, 2], [3, 4])
            if isinstance(n, Point) and len(n.x) >= 1 and len(n.y) >= 1:
                x_val = n.x[0]
                y_val = n.y[0]
                print(x_val, y_val)
            elif isinstance(n, Point):
                print("empty")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y

            n = Point([1, 2], [3, 4])
            match n:
                case Point(x=[x_val, *_], y=[y_val, *_]):
                    print(x_val, y_val)
                case Point():
                    print("empty")
        """
        ).strip()
        
        check_code(source, expected)

    def test_capture_pattern_multi_attribute_multiple_captures(self):
        """Test capturing multiple values from multiple attributes."""
        source = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y

            n = Point([1, 2, 3], [4, 5, 6])
            if isinstance(n, Point) and len(n.x) >= 2 and len(n.y) >= 2:
                x1 = n.x[0]
                x2 = n.x[1]
                y1 = n.y[0]
                y2 = n.y[1]
                print(x1, x2, y1, y2)
            elif isinstance(n, Point):
                print("empty")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y

            n = Point([1, 2, 3], [4, 5, 6])
            match n:
                case Point(x=[x1, x2, *_], y=[y1, y2, *_]):
                    print(x1, x2, y1, y2)
                case Point():
                    print("empty")
        """
        ).strip()
        
        check_code(source, expected)

    def test_capture_pattern_non_consecutive_multi_gap(self):
        """Test non-consecutive with multiple gaps (0, 1, 3, 5)."""
        source = dedent(
            """
            class Data:
                def __init__(self, vals):
                    self.vals = vals

            d = Data([10, 20, 30, 40, 50, 60])
            if isinstance(d, Data) and len(d.vals) >= 6:
                a = d.vals[0]
                b = d.vals[1]
                d_val = d.vals[3]
                f = d.vals[5]
                print(a, b, d_val, f)
            elif isinstance(d, Data):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Data:
                def __init__(self, vals):
                    self.vals = vals

            d = Data([10, 20, 30, 40, 50, 60])
            match d:
                case Data(vals=[a, b, _, d_val, _, f, *_]):
                    print(a, b, d_val, f)
                case Data():
                    print("other")
        """
        ).strip()
        
        check_code(source, expected)

    def test_capture_pattern_not_starting_from_zero(self):
        """Test captures starting from non-zero index."""
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3, 4])
            if isinstance(n, Point) and len(n.x) >= 4:
                second = n.x[1]
                third = n.x[2]
                print(second, third)
            elif isinstance(n, Point):
                print("empty")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            n = Point([1, 2, 3, 4])
            match n:
                case Point(x=[_, second, third, *_]):
                    print(second, third)
                case Point():
                    print("empty")
        """
        ).strip()
        
        check_code(source, expected)

    def test_mixed_pattern_types_in_chain(self):
        """Test that all pattern types can be mixed in a single if/elif chain.

        Demonstrates: literals, isinstance, isinstance+attrs, identity, sequences all together.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x
            class Color:
                pass
            value = [Point(5), 2]
            if len(value) == 2 and isinstance(value[0], Point) and value[1] == 2:
                print("sequence with point")
            elif value == 42:
                print("literal")
            elif isinstance(value, Color):
                print("color")
            elif value is None:
                print("none")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x
            class Color:
                pass
            value = [Point(5), 2]
            match value:
                case Point(), 2:
                    print("sequence with point")
                case 42:
                    print("literal")
                case Color():
                    print("color")
                case None:
                    print("none")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_with_nested_class_in_element(self):
        """Test sequence containing nested class patterns.

        Tests: len(x) == 2 and isinstance(x[0], Container) and isinstance(x[0].inner, Point) (without additional attribute checks)
        This tests that isinstance with nested isinstance works inside sequences.
        """
        source = dedent(
            """
            class Point:
                pass
            class Container:
                def __init__(self, inner):
                    self.inner = inner
            x = [Container(Point()), 5]
            if len(x) == 2 and isinstance(x[0], Container) and x[1] == 5:
                print("sequence with container")
            elif len(x) == 2 and x[0] == 1 and x[1] == 1:
                print("ones")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            class Container:
                def __init__(self, inner):
                    self.inner = inner
            x = [Container(Point()), 5]
            match x:
                case Container(), 5:
                    print("sequence with container")
                case 1, 1:
                    print("ones")
        """
        ).strip()

        check_code(source, expected)

    def test_many_branches_no_limit(self):
        """Test that many elif branches work without limits.

        Demonstrates 12 branches in a single match statement.
        """
        source = dedent(
            """
            x = 5
            if x == 1:
                print("one")
            elif x == 2:
                print("two")
            elif x == 3:
                print("three")
            elif x == 4:
                print("four")
            elif x == 5:
                print("five")
            elif x == 6:
                print("six")
            elif x == 7:
                print("seven")
            elif x == 8:
                print("eight")
            elif x == 9:
                print("nine")
            elif x == 10:
                print("ten")
            elif x == 11:
                print("eleven")
            elif x == 12:
                print("twelve")
        """
        ).strip()

        expected = dedent(
            """
            x = 5
            match x:
                case 1:
                    print("one")
                case 2:
                    print("two")
                case 3:
                    print("three")
                case 4:
                    print("four")
                case 5:
                    print("five")
                case 6:
                    print("six")
                case 7:
                    print("seven")
                case 8:
                    print("eight")
                case 9:
                    print("nine")
                case 10:
                    print("ten")
                case 11:
                    print("eleven")
                case 12:
                    print("twelve")
        """
        ).strip()

        check_code(source, expected)

    def test_complex_real_world_example(self):
        """Test a complex real-world pattern combining multiple features.

        Demonstrates: sequences with isinstance + literals + identity in real usage.
        """
        source = dedent(
            """
            class Request:
                pass
            class Response:
                pass
            class Error:
                pass
            
            message = [Request(), 200, "OK"]
            if len(message) == 3 and isinstance(message[0], Request) and message[1] == 200 and message[2] == "OK":
                print("success request")
            elif len(message) == 3 and isinstance(message[0], Response) and message[1] == 404 and message[2] is None:
                print("not found")
            elif len(message) == 3 and isinstance(message[0], Error) and message[1] == 500 and isinstance(message[2], str):
                print("server error")
            elif isinstance(message, Request):
                print("plain request")
            else:
                print("unknown")
        """
        ).strip()

        expected = dedent(
            """
            class Request:
                pass
            class Response:
                pass
            class Error:
                pass
            
            message = [Request(), 200, "OK"]
            match message:
                case Request(), 200, "OK":
                    print("success request")
                case Response(), 404, None:
                    print("not found")
                case Error(), 500, str():
                    print("server error")
                case Request():
                    print("plain request")
                case _:
                    print("unknown")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_with_nested_sequence_simple(self):
        """Test simple nested sequence: [[1, 2], 3]."""
        source = dedent(
            """
            x = [[1, 2], 3]
            if len(x) == 2 and len(x[0]) == 2 and x[0][0] == 1 and x[0][1] == 2 and x[1] == 3:
                print("match")
            elif x == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            x = [[1, 2], 3]
            match x:
                case [1, 2], 3:
                    print("match")
                case 0:
                    print("zero")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_with_nested_sequence_and_isinstance(self):
        """Test nested sequence mixed with isinstance: [Point(), [1, 2]]."""
        source = dedent(
            """
            class Point:
                pass
            
            z = [Point(), [1, 2]]
            if len(z) == 2 and isinstance(z[0], Point) and len(z[1]) == 2 and z[1][0] == 1 and z[1][1] == 2:
                print("match")
            elif z == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            
            z = [Point(), [1, 2]]
            match z:
                case Point(), [1, 2]:
                    print("match")
                case 0:
                    print("zero")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_with_nested_sequence_strings(self):
        """Test nested sequence with strings: [["a", "b"], "c"]."""
        source = dedent(
            """
            x = [["a", "b"], "c"]
            if len(x) == 2 and len(x[0]) == 2 and x[0][0] == "a" and x[0][1] == "b" and x[1] == "c":
                print("match")
            elif x == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            x = [["a", "b"], "c"]
            match x:
                case ["a", "b"], "c":
                    print("match")
                case 0:
                    print("zero")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_with_multiple_nested_sequences(self):
        """Test multiple nested sequences in one pattern: [[1, 2], [3, 4]]."""
        source = dedent(
            """
            x = [[1, 2], [3, 4]]
            if len(x) == 2 and len(x[0]) == 2 and x[0][0] == 1 and x[0][1] == 2 and len(x[1]) == 2 and x[1][0] == 3 and x[1][1] == 4:
                print("match")
            elif x == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            x = [[1, 2], [3, 4]]
            match x:
                case [1, 2], [3, 4]:
                    print("match")
                case 0:
                    print("zero")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_sequence_attribute_converted(self):
        """Test that isinstance with sequence attributes converts to class patterns.

        Patterns like 'isinstance(obj, Data) and len(obj.value) == 3 and obj.value[0] == 1'
        become 'case Data(value=[1, 2, 3]):'.
        """
        source = dedent(
            """
            class Data:
                def __init__(self, value):
                    self.value = value
            
            obj = Data([1, 2, 3])
            if isinstance(obj, Data) and len(obj.value) == 3 and obj.value[0] == 1 and obj.value[1] == 2 and obj.value[2] == 3:
                print("match")
            elif isinstance(obj, Data):
                print("other data")
        """
        ).strip()

        expected = dedent(
            """
            class Data:
                def __init__(self, value):
                    self.value = value
            
            obj = Data([1, 2, 3])
            match obj:
                case Data(value=[1, 2, 3]):
                    print("match")
                case Data():
                    print("other data")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_sequence_attribute_mixed_types(self):
        """Test class pattern with sequence attribute containing mixed types."""
        source = dedent(
            """
            class Point:
                pass
            
            class Data:
                def __init__(self, value):
                    self.value = value
            
            obj = Data([Point(), 1, 2])
            if isinstance(obj, Data) and len(obj.value) == 3 and isinstance(obj.value[0], Point) and obj.value[1] == 1 and obj.value[2] == 2:
                print("match")
            elif isinstance(obj, Data):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                pass
            
            class Data:
                def __init__(self, value):
                    self.value = value
            
            obj = Data([Point(), 1, 2])
            match obj:
                case Data(value=[Point(), 1, 2]):
                    print("match")
                case Data():
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_sequence_and_scalar_attributes(self):
        """Test class pattern with both sequence and scalar attributes."""
        source = dedent(
            """
            class Container:
                def __init__(self, items, count):
                    self.items = items
                    self.count = count
            
            obj = Container([1, 2, 3], 3)
            if isinstance(obj, Container) and len(obj.items) == 3 and obj.items[0] == 1 and obj.items[1] == 2 and obj.items[2] == 3 and obj.count == 3:
                print("match")
            elif isinstance(obj, Container):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Container:
                def __init__(self, items, count):
                    self.items = items
                    self.count = count
            
            obj = Container([1, 2, 3], 3)
            match obj:
                case Container(items=[1, 2, 3], count=3):
                    print("match")
                case Container():
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_nested_sequence_attributes(self):
        """Test nested isinstance with sequence attributes.

        Pattern like Data(value=[Data(value=[1,2,3])]) now fully converts with nested attributes.
        """
        source = dedent(
            """
            class Data:
                def __init__(self, value):
                    self.value = value
            
            inner = Data([1, 2, 3])
            outer = Data([inner])
            if isinstance(outer, Data) and len(outer.value) == 1 and isinstance(outer.value[0], Data) and len(outer.value[0].value) == 3 and outer.value[0].value[0] == 1 and outer.value[0].value[1] == 2 and outer.value[0].value[2] == 3:
                print("match")
            elif isinstance(outer, Data):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Data:
                def __init__(self, value):
                    self.value = value
            
            inner = Data([1, 2, 3])
            outer = Data([inner])
            match outer:
                case Data(value=[Data(value=[1, 2, 3])]):
                    print("match")
                case Data():
                    print("other")
        """
        ).strip()

        check_code(source, expected)


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


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_isinstance_with_starred_element_not_converted(self):
        """Test that isinstance with *args in tuple is not converted."""
        source = dedent(
            """
            types = (int, str)
            value = 42
            if isinstance(value, (*types,)):
                print("matches")
            elif value == 0:
                print("zero")
        """
        ).strip()

        # Expected is same as source (no transformation due to starred element)
        expected = source
        check_code(source, expected)

    def test_isinstance_with_empty_tuple_not_converted(self):
        """Test that isinstance with empty tuple is not converted."""
        source = dedent(
            """
            x = 42
            if isinstance(x, ()):
                print("empty tuple")
            elif x == 42:
                print("forty two")
        """
        ).strip()

        # Expected is same as source (no transformation - empty tuple not supported)
        expected = source
        check_code(source, expected)

    def test_unknown_pattern_type_raises_error(self):
        """Test that unknown pattern type raises ValueError."""
        transformer = IfToMatchTransformer()
        
        with pytest.raises(ValueError, match="Unknown pattern type"):
            transformer._build_pattern_from_info(("unknown_type", None))

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

    def test_isinstance_tuple_with_attributes_not_converted(self):
        """Test that isinstance with tuple of classes AND attributes is not converted.
        
        This is not supported because we can't determine which class's attributes to check.
        """
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x
            class Line:
                def __init__(self, x):
                    self.x = x
            
            obj = Point(5)
            if isinstance(obj, (Point, Line)) and obj.x == 5:
                print("match")
            elif obj == 0:
                print("zero")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_isinstance_with_non_literal_attribute_not_converted(self):
        """Test that isinstance with variable in attribute check is not converted."""
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x
            
            TARGET = 5
            obj = Point(5)
            if isinstance(obj, Point) and obj.x == TARGET:
                print("match")
            elif isinstance(obj, Point):
                print("other")
        """
        ).strip()

        # Expected is same as source (no transformation - variable not literal)
        expected = source
        check_code(source, expected)

    def test_isinstance_with_type_variable_ignored(self):
        """Test that isinstance with type variables matching --no-types pattern are not converted."""
        source = dedent(
            """
            SYMBOL_TYPES = (FuncDef, OverloadedFuncDef)
            
            n = None
            if isinstance(n, SYMBOL_TYPES):
                print("match")
            elif isinstance(n, int):
                print("int")
        """
        ).strip()

        # With default --no-types pattern (.*_TYPES$), this should NOT be converted
        expected = source
        check_code(source, expected)
        
        # Without the pattern, it should convert
        expected_converted = dedent(
            """
            SYMBOL_TYPES = (FuncDef, OverloadedFuncDef)
            
            n = None
            match n:
                case SYMBOL_TYPES():
                    print("match")
                case int():
                    print("int")
        """
        ).strip()
        check_code(source, expected_converted, ignore_types_pattern=None)

    def test_guard_pattern_with_boolean_attribute(self):
        """Test isinstance with boolean attribute as guard (not comparison)."""
        source = dedent(
            """
            class TupleType:
                pass
            
            item = TupleType()
            if isinstance(item, TupleType) and item.is_valid:
                print("valid tuple")
            elif isinstance(item, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class TupleType:
                pass
            
            item = TupleType()
            match item:
                case TupleType() if item.is_valid:
                    print("valid tuple")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_guard_pattern_with_nested_boolean_attribute(self):
        """Test isinstance with deeply nested boolean attribute as guard."""
        source = dedent(
            """
            class TupleType:
                pass
            
            item = TupleType()
            if isinstance(item, TupleType) and item.partial_fallback.type.is_named_tuple:
                print("named tuple")
            elif isinstance(item, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class TupleType:
                pass
            
            item = TupleType()
            match item:
                case TupleType() if item.partial_fallback.type.is_named_tuple:
                    print("named tuple")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_nested_isinstance_on_attributes(self):
        """Test isinstance with nested isinstance checks on attributes.
        
        Pattern: isinstance(x, Class1) and isinstance(x.attr, Class2)
        Should become: case Class1(attr=Class2()):
        """
        source = dedent(
            """
            class NameExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                pass
            
            lvalue = NameExpr(Var())
            if isinstance(lvalue, NameExpr) and isinstance(lvalue.node, Var):
                print("match")
            elif isinstance(lvalue, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class NameExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                pass
            
            lvalue = NameExpr(Var())
            match lvalue:
                case NameExpr(node=Var()):
                    print("match")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_deeply_nested_isinstance_on_attributes(self):
        """Test isinstance with deeply nested isinstance checks.
        
        Pattern: isinstance(x, A) and isinstance(x.b, B) and isinstance(x.b.c, C)
        Should become: case A(b=B(c=C())):
        """
        source = dedent(
            """
            class NameExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                def __init__(self, type=None):
                    self.type = type
            
            class PartialType:
                pass
            
            lvalue = NameExpr(Var(PartialType()))
            if isinstance(lvalue, NameExpr) and isinstance(lvalue.node, Var) and isinstance(lvalue.node.type, PartialType):
                print("match")
            elif isinstance(lvalue, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class NameExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                def __init__(self, type=None):
                    self.type = type
            
            class PartialType:
                pass
            
            lvalue = NameExpr(Var(PartialType()))
            match lvalue:
                case NameExpr(node=Var(type=PartialType())):
                    print("match")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_nested_isinstance_and_attr_checks(self):
        """Test that nested isinstance with attribute checks on nested paths are converted."""
        source = dedent(
            """
            class NameExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                def __init__(self, type=None):
                    self.type = type
            
            lv = NameExpr(Var(None))
            if isinstance(lv, NameExpr) and isinstance(lv.node, Var) and lv.node.type is None:
                print("match")
            elif isinstance(lv, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class NameExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                def __init__(self, type=None):
                    self.type = type
            
            lv = NameExpr(Var(None))
            match lv:
                case NameExpr(node=Var(type=None)):
                    print("match")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_nested_isinstance_and_multiple_attr_checks(self):
        """Test nested isinstance with multiple attribute checks on nested paths."""
        source = dedent(
            """
            class Point:
                def __init__(self, data=None):
                    self.data = data
            
            class Data:
                def __init__(self, x=0, y=0):
                    self.x = x
                    self.y = y
            
            obj = Point(Data(5, 10))
            if isinstance(obj, Point) and isinstance(obj.data, Data) and obj.data.x == 5 and obj.data.y == 10:
                print("match")
            elif isinstance(obj, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, data=None):
                    self.data = data
            
            class Data:
                def __init__(self, x=0, y=0):
                    self.x = x
                    self.y = y
            
            obj = Point(Data(5, 10))
            match obj:
                case Point(data=Data(x=5, y=10)):
                    print("match")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_nested_isinstance_tuple(self):
        """Test nested isinstance with tuple of classes on nested attribute."""
        source = dedent(
            """
            class RefExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                pass
            
            class FuncDef:
                pass
            
            class CallExpr:
                def __init__(self, callee=None):
                    self.callee = callee
            
            class Decorator:
                pass
            
            dec = RefExpr(Var())
            if isinstance(dec, RefExpr) and isinstance(dec.node, (Var, FuncDef)):
                print("case 1")
            elif isinstance(dec, CallExpr) and isinstance(dec.callee, RefExpr) and isinstance(dec.callee.node, (Decorator, FuncDef, Var)):
                print("case 2")
        """
        ).strip()

        expected = dedent(
            """
            class RefExpr:
                def __init__(self, node=None):
                    self.node = node
            
            class Var:
                pass
            
            class FuncDef:
                pass
            
            class CallExpr:
                def __init__(self, callee=None):
                    self.callee = callee
            
            class Decorator:
                pass
            
            dec = RefExpr(Var())
            match dec:
                case RefExpr(node=Var() | FuncDef()):
                    print("case 1")
                case CallExpr(callee=RefExpr(node=Decorator() | FuncDef() | Var())):
                    print("case 2")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_type_variable_in_tuple_ignored(self):
        """Test that isinstance with tuple containing type variables is not converted."""
        source = dedent(
            """
            SYMBOL_FUNCBASE_TYPES = (FuncDef, OverloadedFuncDef)
            
            class Var:
                pass
            
            node = Var()
            if isinstance(node, (Var, SYMBOL_FUNCBASE_TYPES)):
                print("match")
            elif isinstance(node, int):
                print("int")
        """
        ).strip()

        # With default --no-types pattern (.*_TYPES$), this should NOT be converted
        # because SYMBOL_FUNCBASE_TYPES is in the tuple
        expected = source
        check_code(source, expected)
        
        # Without the pattern, it should convert
        expected_converted = dedent(
            """
            SYMBOL_FUNCBASE_TYPES = (FuncDef, OverloadedFuncDef)
            
            class Var:
                pass
            
            node = Var()
            match node:
                case Var() | SYMBOL_FUNCBASE_TYPES():
                    print("match")
                case int():
                    print("int")
        """
        ).strip()
        check_code(source, expected_converted, ignore_types_pattern=None)

    def test_sequence_with_non_integer_subscript_not_converted(self):
        """Test that sequences with non-integer indices are not converted."""
        source = dedent(
            """
            x = {"a": 1, "b": 2}
            # This would be x["a"] which we don't support
            if len(x) == 2:
                print("two items")
            elif x == 0:
                print("zero")
        """
        ).strip()

        # Expected is same as source (no transformation)
        expected = source
        check_code(source, expected)

    def test_is_operator_with_non_singleton_not_converted(self):
        """Test that 'is' operator with non-singletons (not None/True/False) is not converted."""
        source = dedent(
            """
            SENTINEL = object()
            x = SENTINEL
            if x is SENTINEL:
                print("sentinel")
            elif x == 1:
                print("one")
        """
        ).strip()

        # Expected is same as source (no transformation - is with non-singleton)
        expected = source
        check_code(source, expected)

    def test_walrus_operator_in_isinstance_not_converted(self):
        """Test that isinstance with walrus operator (NamedExpr) is not converted."""
        source = dedent(
            """
            class CallExpr:
                pass
            
            class CallableType:
                pass
            
            def get_type(x):
                return CallableType()
            
            obj = CallExpr()
            if isinstance(obj, CallExpr) and isinstance((call_tp := get_type(obj)), CallableType):
                print("matched")
            elif obj == None:
                print("none")
        """
        ).strip()

        # Expected is same as source (no transformation - walrus operator cannot be converted)
        expected = source
        check_code(source, expected)

    def test_mixed_sequence_patterns_in_chain(self):
        """Test multiple sequence patterns in same chain."""
        source = dedent(
            """
            point = (1, 2)
            if len(point) == 2 and point[0] == 1 and point[1] == 2:
                print("1, 2")
            elif len(point) == 2 and point[0] == 0 and point[1] == 0:
                print("0, 0")
            elif len(point) == 3 and point[0] == 1 and point[1] == 1 and point[2] == 1:
                print("1, 1, 1")
        """
        ).strip()

        expected = dedent(
            """
            point = (1, 2)
            match point:
                case 1, 2:
                    print("1, 2")
                case 0, 0:
                    print("0, 0")
                case 1, 1, 1:
                    print("1, 1, 1")
        """
        ).strip()

        check_code(source, expected)

    def test_guard_pattern_with_independent_condition(self):
        """Test isinstance with guard clause that doesn't reference the subject."""
        source = dedent(
            """
            import os
            
            class FileHandler:
                pass
            
            handler = FileHandler()
            if isinstance(handler, FileHandler) and os.path.exists("/tmp"):
                print("handler with file")
            elif handler == None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            import os
            
            class FileHandler:
                pass
            
            handler = FileHandler()
            match handler:
                case FileHandler() if os.path.exists("/tmp"):
                    print("handler with file")
                case None:
                    print("none")
        """
        ).strip()

        check_code(source, expected)

    def test_guard_pattern_with_global_variable(self):
        """Test isinstance with guard that uses global variable."""
        source = dedent(
            """
            ENABLED = True
            
            class Config:
                pass
            
            cfg = Config()
            if isinstance(cfg, Config) and ENABLED:
                print("enabled config")
            elif cfg == None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            ENABLED = True
            
            class Config:
                pass
            
            cfg = Config()
            match cfg:
                case Config() if ENABLED:
                    print("enabled config")
                case None:
                    print("none")
        """
        ).strip()

        check_code(source, expected)

    def test_guard_pattern_with_multiple_conditions(self):
        """Test isinstance with multiple independent guard conditions."""
        source = dedent(
            """
            DEBUG = True
            VERBOSE = False
            
            class Logger:
                pass
            
            log = Logger()
            if isinstance(log, Logger) and DEBUG and not VERBOSE:
                print("debug logger")
            elif log == None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            DEBUG = True
            VERBOSE = False
            
            class Logger:
                pass
            
            log = Logger()
            match log:
                case Logger() if DEBUG and not VERBOSE:
                    print("debug logger")
                case None:
                    print("none")
        """
        ).strip()

        check_code(source, expected)

    def test_guard_pattern_with_multiple_classes(self):
        """Test isinstance with tuple of classes and independent guard."""
        source = dedent(
            """
            PRODUCTION = True
            
            class Handler:
                pass
            
            class Worker:
                pass
            
            obj = Handler()
            if isinstance(obj, (Handler, Worker)) and PRODUCTION:
                print("production mode")
            elif obj == None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            PRODUCTION = True
            
            class Handler:
                pass
            
            class Worker:
                pass
            
            obj = Handler()
            match obj:
                case Handler() | Worker() if PRODUCTION:
                    print("production mode")
                case None:
                    print("none")
        """
        ).strip()

        check_code(source, expected)

    def test_guard_pattern_with_isinstance_check(self):
        """Test isinstance guard with another isinstance check on different variable."""
        source = dedent(
            """
            class ParamSpecType:
                pass
            
            tvar = ParamSpecType()
            mapped_arg = ParamSpecType()
            if isinstance(tvar, ParamSpecType) and isinstance(mapped_arg, ParamSpecType):
                print("both are ParamSpecType")
            elif isinstance(tvar, ParamSpecType):
                print("only tvar")
        """
        ).strip()

        expected = dedent(
            """
            class ParamSpecType:
                pass
            
            tvar = ParamSpecType()
            mapped_arg = ParamSpecType()
            match tvar:
                case ParamSpecType() if isinstance(mapped_arg, ParamSpecType):
                    print("both are ParamSpecType")
                case ParamSpecType():
                    print("only tvar")
        """
        ).strip()

        check_code(source, expected)

    def test_comment_preservation_before_if(self):
        """Test that comments before if statements are preserved."""
        source = dedent(
            """
            class Decorator:
                pass
            
            item = Decorator()
            
            # TODO: support decorated overloaded functions properly
            if isinstance(item, Decorator):
                print("decorator")
            elif isinstance(item, int):
                print("int")
        """
        ).strip()

        expected = dedent(
            """
            class Decorator:
                pass
            
            item = Decorator()
            
            # TODO: support decorated overloaded functions properly
            match item:
                case Decorator():
                    print("decorator")
                case int():
                    print("int")
        """
        ).strip()

        check_code(source, expected)

    def test_comment_preservation_before_elif_and_else(self):
        """Test that comments before elif and else are preserved."""
        source = dedent(
            """
            class Decorator:
                pass
            
            class Handler:
                pass
            
            item = Decorator()
            
            # Comment before if
            if isinstance(item, Decorator):
                print("decorator")
            # Comment before elif
            elif isinstance(item, Handler):
                print("handler")
            # Comment before else
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Decorator:
                pass
            
            class Handler:
                pass
            
            item = Decorator()
            
            # Comment before if
            match item:
                case Decorator():
                    print("decorator")
                # Comment before elif
                case Handler():
                    print("handler")
                # Comment before else
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, expected)
