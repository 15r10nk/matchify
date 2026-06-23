from textwrap import dedent

from helpers import check_code


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

    def test_isinstance_with_len_check_on_attribute_not_converted(self):
        """Test that isinstance with len() check on attribute is not converted.

        Regression test for bug where len(o.args) == 2 was being silently dropped.
        The pattern should not be converted because we can't (yet) mix attribute
        patterns with guard conditions on non-subject attributes.
        """
        source = dedent(
            """
            class RefExpr:
                def __init__(self, fullname, args=None):
                    self.fullname = fullname
                    self.args = args if args else []

            class CallExpr:
                def __init__(self, callee):
                    self.callee = callee

            o = CallExpr(RefExpr("builtins.isinstance", [1, 2]))
            if isinstance(o.callee, RefExpr) and o.callee.fullname == "builtins.isinstance" and len(o.callee.args) == 2:
                print("isinstance with 2 args")
            elif isinstance(o.callee, RefExpr):
                print("other RefExpr")
        """
        ).strip()

        # Expected is same as source (no transformation - len() on attribute not supported)
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

    def test_isinstance_with_nested_class_sequence_attribute(self):
        """Test sequence attributes inside a nested class attribute."""
        source = dedent(
            """
            class Point:
                def __init__(self, data=None):
                    self.data = data

            class Data:
                def __init__(self, kind=None):
                    self.kind = kind

            obj = Point(Data([1, 2]))
            if isinstance(obj, Point) and isinstance(obj.data, Data) and len(obj.data.kind) == 2 and obj.data.kind[0] == 1 and obj.data.kind[1] == 2:
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
                def __init__(self, kind=None):
                    self.kind = kind

            obj = Point(Data([1, 2]))
            match obj:
                case Point(data=Data(kind=[1, 2])):
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

    def test_is_not_operator_not_converted(self):
        """Test that 'is not' chains are not converted to singleton patterns."""
        source = dedent(
            """
            x = None
            if x is not None:
                print("value")
            elif x is None:
                print("none")
        """
        ).strip()

        expected = source
        check_code(source, expected)

    def test_chained_comparison_not_converted(self):
        """Test that chained comparisons are left alone even with a convertible elif."""
        source = dedent(
            """
            x = 1
            if 0 < x < 10:
                print("range")
            elif x == 20:
                print("twenty")
        """
        ).strip()

        expected = source
        check_code(source, expected)

    def test_walrus_operator_in_isinstance_subject_not_converted(self):
        """Test that walrus assignment in the match subject position is preserved."""
        source = dedent(
            """
            class Node:
                pass

            if isinstance((node := Node()), Node):
                print("node")
            elif isinstance(node, int):
                print("int")
        """
        ).strip()

        expected = source
        check_code(source, expected)

    def test_walrus_operator_in_isinstance_converted_to_guard(self):
        """Test that isinstance with walrus operator is converted to guard clause."""
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

        expected = dedent(
            """
            class CallExpr:
                pass

            class CallableType:
                pass

            def get_type(x):
                return CallableType()

            obj = CallExpr()
            match obj:
                case CallExpr() if isinstance((call_tp := get_type(obj)), CallableType):
                    print("matched")
                case None:
                    print("none")
        """
        ).strip()
        check_code(source, expected)

    def test_non_equality_condition_after_pattern_becomes_guard(self):
        """Test that unsupported comparisons after a class pattern stay as guards."""
        source = dedent(
            """
            class Node:
                pass

            node = Node()
            if isinstance(node, Node) and node != None:
                print("not none")
            elif node is None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            class Node:
                pass

            node = Node()
            match node:
                case Node() if node != None:
                    print("not none")
                case None:
                    print("none")
        """
        ).strip()

        check_code(source, expected)

    def test_parenthesized_or_condition_after_pattern_becomes_guard(self):
        """Test that parenthesized OR conditions are preserved as guard expressions."""
        source = dedent(
            """
            ready = False
            forced = True

            class Handler:
                pass

            handler = Handler()
            if isinstance(handler, Handler) and (ready or forced):
                print("go")
            elif handler is None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            ready = False
            forced = True

            class Handler:
                pass

            handler = Handler()
            match handler:
                case Handler() if (ready or forced):
                    print("go")
                case None:
                    print("none")
        """
        ).strip()

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

    def test_guard_pattern_with_ignored_type_check_on_other_subject(self):
        """Type variables on guard-only subjects stay guards instead of blocking conversion."""
        source = dedent(
            """
            OTHER_TYPES = (int,)

            class Handler:
                pass

            handler = Handler()
            value = 1
            if isinstance(handler, Handler) and isinstance(value, OTHER_TYPES):
                print("typed handler")
            elif handler is None:
                print("none")
        """
        ).strip()

        expected = dedent(
            """
            OTHER_TYPES = (int,)

            class Handler:
                pass

            handler = Handler()
            value = 1
            match handler:
                case Handler() if isinstance(value, OTHER_TYPES):
                    print("typed handler")
                case None:
                    print("none")
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

    def test_nested_isinstance_with_walrus_converted_to_pattern_and_guard(self):
        """Test that nested isinstance with walrus combines pattern + guard clause."""
        source = dedent(
            """
            class CallExpr:
                def __init__(self, callee=None):
                    self.callee = callee

            class RefExpr:
                def __init__(self, node=None):
                    self.node = node

            class Decorator:
                def __init__(self):
                    self.type = None

            class FuncDef:
                def __init__(self):
                    self.type = None

            class Var:
                def __init__(self):
                    self.type = None

            class CallableType:
                pass

            def get_proper_type(x):
                return CallableType()

            dec = CallExpr(RefExpr(Var()))
            if isinstance(dec, CallExpr) and isinstance(dec.callee, RefExpr) and isinstance(dec.callee.node, (Decorator, FuncDef, Var)) and isinstance((call_tp := get_proper_type(dec.callee.node.type)), CallableType):
                print("matched")
            elif isinstance(dec, RefExpr):
                print("refexpr")
        """
        ).strip()

        expected = dedent(
            """
            class CallExpr:
                def __init__(self, callee=None):
                    self.callee = callee

            class RefExpr:
                def __init__(self, node=None):
                    self.node = node

            class Decorator:
                def __init__(self):
                    self.type = None

            class FuncDef:
                def __init__(self):
                    self.type = None

            class Var:
                def __init__(self):
                    self.type = None

            class CallableType:
                pass

            def get_proper_type(x):
                return CallableType()

            dec = CallExpr(RefExpr(Var()))
            match dec:
                case CallExpr(callee=RefExpr(node=Decorator() | FuncDef() | Var())) if isinstance((call_tp := get_proper_type(dec.callee.node.type)), CallableType):
                    print("matched")
                case RefExpr():
                    print("refexpr")
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_proper_type_with_second_isinstance_becomes_guard(self):
        """Test that isinstance(x, ProperType) and isinstance(x, (AnyType, UninhabitedType)) becomes a guard."""
        source = dedent(
            """
            class TypeVarTupleType:
                pass

            class ProperType:
                pass

            class AnyType(ProperType):
                pass

            class UninhabitedType(ProperType):
                pass

            t = TypeVarTupleType()
            repl = t
            if isinstance(repl, TypeVarTupleType):
                result = repl
            elif isinstance(repl, ProperType) and isinstance(repl, (AnyType, UninhabitedType)):
                result = "any or uninhabited"
            else:
                result = "other"
        """
        ).strip()

        expected = dedent(
            """
            class TypeVarTupleType:
                pass

            class ProperType:
                pass

            class AnyType(ProperType):
                pass

            class UninhabitedType(ProperType):
                pass

            t = TypeVarTupleType()
            repl = t
            match repl:
                case TypeVarTupleType():
                    result = repl
                case ProperType() if isinstance(repl, (AnyType, UninhabitedType)):
                    result = "any or uninhabited"
                case _:
                    result = "other"
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_attribute_guard_converted(self):
        """Test that isinstance(x, Class) and x.attr converts to case Class() if x.attr:"""
        source = dedent(
            """
            class Instance:
                def __init__(self):
                    self.args = []

            class TupleType:
                pass

            class ParamSpecType:
                pass

            def get_proper_type(x):
                return x

            actual_type = Instance()
            if isinstance(actual_type, Instance) and actual_type.args:
                result = "instance with args"
            elif isinstance(actual_type, TupleType):
                result = "tuple"
            elif isinstance(actual_type, ParamSpecType):
                result = "paramspec"
            else:
                result = "other"
        """
        ).strip()

        expected = dedent(
            """
            class Instance:
                def __init__(self):
                    self.args = []

            class TupleType:
                pass

            class ParamSpecType:
                pass

            def get_proper_type(x):
                return x

            actual_type = Instance()
            match actual_type:
                case Instance() if actual_type.args:
                    result = "instance with args"
                case TupleType():
                    result = "tuple"
                case ParamSpecType():
                    result = "paramspec"
                case _:
                    result = "other"
        """
        ).strip()

        check_code(source, expected)

    def test_isinstance_with_boolean_attribute_guard_real_world(self):
        """Test real-world pattern from mypy: isinstance + boolean attribute."""
        source = dedent(
            """
            class Instance:
                def __init__(self):
                    self.args = []

            class TupleType:
                pass

            class ParamSpecType:
                pass

            class AnyType:
                pass

            def get_proper_type(x):
                return x

            actual_type = get_proper_type(Instance())
            if isinstance(actual_type, Instance) and actual_type.args:
                from mypy.subtypes import is_subtype
                result = "instance"
            elif isinstance(actual_type, TupleType):
                result = "tuple"
            elif isinstance(actual_type, ParamSpecType):
                result = "paramspec"
            else:
                result = AnyType()
        """
        ).strip()

        expected = dedent(
            """
            class Instance:
                def __init__(self):
                    self.args = []

            class TupleType:
                pass

            class ParamSpecType:
                pass

            class AnyType:
                pass

            def get_proper_type(x):
                return x

            actual_type = get_proper_type(Instance())
            match actual_type:
                case Instance() if actual_type.args:
                    from mypy.subtypes import is_subtype
                    result = "instance"
                case TupleType():
                    result = "tuple"
                case ParamSpecType():
                    result = "paramspec"
                case _:
                    result = AnyType()
        """
        ).strip()

        check_code(source, expected)
