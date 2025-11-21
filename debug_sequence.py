class A:
    def check_except_handler_test(self, n: Expression, is_star: bool) -> Type:
        """Type check an exception handler test clause."""
        typ = self.expr_checker.accept(n)

        all_types: list[Type] = []
        test_types = self.get_types_from_except_handler(typ, n)

        for ttype in get_proper_types(test_types):
            if isinstance(ttype, AnyType):
                all_types.append(ttype)
                continue
            match ttype:
                case FunctionLike():
                    item = ttype.items[0]
                    if not item.is_type_obj():
                        self.fail(message_registry.INVALID_EXCEPTION_TYPE, n)
                        return self.default_exception_type(is_star)
                    exc_type = erase_typevars(item.ret_type)
                case TypeType():
                    exc_type = ttype.item
                case _:
                    self.fail(message_registry.INVALID_EXCEPTION_TYPE, n)
                    return self.default_exception_type(is_star)

            if not is_subtype(exc_type, self.named_type("builtins.BaseException")):
                self.fail(message_registry.INVALID_EXCEPTION_TYPE, n)
                return self.default_exception_type(is_star)

            all_types.append(exc_type)
