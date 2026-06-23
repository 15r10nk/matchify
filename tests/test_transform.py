from textwrap import dedent

from helpers import check_code


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

    def test_sequence_pattern_with_class_element_attributes(self):
        """Test class attributes on an element inside a sequence pattern."""
        source = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            value = [Point(1, 2)]
            if len(value) == 1 and isinstance(value[0], Point) and value[0].x == 1 and value[0].y == 2:
                print("match")
            elif value == 1:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y
            value = [Point(1, 2)]
            match value:
                case Point(x=1, y=2),:
                    print("match")
                case 1:
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_sequence_pattern_with_nested_class_element_attributes(self):
        """Test nested class attributes on an element inside a sequence pattern."""
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            class Node:
                def __init__(self, kind):
                    self.kind = kind

            value = [Point(Node("ready"))]
            if len(value) == 1 and isinstance(value[0], Point) and isinstance(value[0].x, Node) and value[0].x.kind == "ready":
                print("match")
            elif value == 1:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            class Node:
                def __init__(self, kind):
                    self.kind = kind

            value = [Point(Node("ready"))]
            match value:
                case Point(x=Node(kind="ready")),:
                    print("match")
                case 1:
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

    def test_sequence_pattern_with_or_element(self):
        """Test OR patterns inside a sequence element."""
        source = dedent(
            """
            value = [2, 3]
            if len(value) == 2 and (value[0] == 1 or value[0] == 2) and value[1] == 3:
                print("match")
            elif value == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            value = [2, 3]
            match value:
                case 1 | 2, 3:
                    print("match")
                case 0:
                    print("zero")
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

    def test_sequence_pattern_with_isinstance_tuple_and_attribute(self):
        """Test attributes on an isinstance tuple inside a sequence pattern."""
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            class Node:
                def __init__(self, x):
                    self.x = x

            value = [Node(1)]
            if len(value) == 1 and isinstance(value[0], (Point, Node)) and value[0].x == 1:
                print("match")
            elif value == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            class Node:
                def __init__(self, x):
                    self.x = x

            value = [Node(1)]
            match value:
                case Point(x=1) | Node(x=1),:
                    print("match")
                case 0:
                    print("zero")
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
            """
            status = "ready"
            if status == "ready" or status == "running":
                print("active")
            elif status == "stopped" or status == "error":
                print("inactive")
        """
        ).strip()

        expected = dedent(
            """
            status = "ready"
            match status:
                case "ready" | "running":
                    print("active")
                case "stopped" | "error":
                    print("inactive")
        """
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

    def test_sequence_with_nested_star_sequence(self):
        """Test nested open-ended sequence: [[1, 2, ...], 3]."""
        source = dedent(
            """
            x = [[1, 2, 99], 3]
            if len(x) == 2 and len(x[0]) >= 2 and x[0][0] == 1 and x[0][1] == 2 and x[1] == 3:
                print("match")
            elif x == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            x = [[1, 2, 99], 3]
            match x:
                case [1, 2, *_], 3:
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

    def test_sequence_with_deeply_nested_sequence(self):
        """Test recursive nested sequences: [[[1, 2]]]."""
        source = dedent(
            """
            x = [[[1, 2]]]
            if len(x) == 1 and len(x[0]) == 1 and len(x[0][0]) == 2 and x[0][0][0] == 1 and x[0][0][1] == 2:
                print("match")
            elif x == 0:
                print("zero")
        """
        ).strip()

        expected = dedent(
            """
            x = [[[1, 2]]]
            match x:
                case [[1, 2]],:
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

    def test_isinstance_with_or_attribute(self):
        """Test OR patterns inside a class attribute."""
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            value = Point(2)
            if isinstance(value, Point) and (value.x == 1 or value.x == 2):
                print("match")
            elif isinstance(value, Point):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            value = Point(2)
            match value:
                case Point(x=1 | 2):
                    print("match")
                case Point():
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_nested_sequence_in_sequence_attribute(self):
        """Test raw nested sequences inside a class sequence attribute."""
        source = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            value = Point([[1, 2]])
            if isinstance(value, Point) and len(value.x) == 1 and len(value.x[0]) == 2 and value.x[0][0] == 1 and value.x[0][1] == 2:
                print("match")
            elif isinstance(value, Point):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Point:
                def __init__(self, x):
                    self.x = x

            value = Point([[1, 2]])
            match value:
                case Point(x=[[1, 2]]):
                    print("match")
                case Point():
                    print("other")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_sequence_and_nested_class_attributes(self):
        """Test class pattern with both sequence and nested class attributes."""
        source = dedent(
            """
            class Node:
                pass

            class Token:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y

            value = Node()
            value.kind = [Node(), True]
            value.y = Token('ready', 0)
            if isinstance(value, Node) and len(value.kind) == 2 and isinstance(value.kind[0], Node) and value.kind[1] is True and isinstance(value.y, Token) and value.y.x == 'ready' and value.y.y == 0:
                print("match")
            elif isinstance(value, Node):
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Node:
                pass

            class Token:
                def __init__(self, x, y):
                    self.x = x
                    self.y = y

            value = Node()
            value.kind = [Node(), True]
            value.y = Token('ready', 0)
            match value:
                case Node(kind=[Node(), True], y=Token(x='ready', y=0)):
                    print("match")
                case Node():
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
