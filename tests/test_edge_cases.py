from textwrap import dedent

from helpers import check_code


class TestEdgeCases:
    """Test edge cases and error handling."""

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

    def test_isinstance_with_qualified_ignored_type(self):
        source = dedent(
            """
            import typing

            value = {"a": "b"}
            if isinstance(value, typing.Mapping):
                print("mapping")
            elif isinstance(value, str):
                print("string")

            other = {"a": "b"}
            if isinstance(other, (str, typing.Mapping)):
                print("string or mapping")
            elif isinstance(other, bytes):
                print("bytes")
            """
        ).strip()

        check_code(source, source, ignore_types_pattern=r"typing\.Mapping")

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
