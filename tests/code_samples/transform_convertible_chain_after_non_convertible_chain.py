# before:
class CallableType:
    min_args = 1


class Overloaded:
    pass


class FunctionLike:
    pass


class TypeType:
    item = "error"


override = CallableType()
original = CallableType()
test_types = [TypeType()]

# This chain converts with the variable comparison preserved as a guard.
if isinstance(override, CallableType) and override.min_args == original.min_args:
    override_kind = "matching callable"
elif isinstance(override, Overloaded):
    override_kind = "overloaded"
print(override_kind)

# This chain SHOULD be converted (independent, valid pattern)
for ttype in test_types:
    if isinstance(ttype, FunctionLike):
        pass
    elif isinstance(ttype, TypeType):
        exc_type = ttype.item
    else:
        pass
print(exc_type)

# after:
class CallableType:
    min_args = 1


class Overloaded:
    pass


class FunctionLike:
    pass


class TypeType:
    item = "error"


override = CallableType()
original = CallableType()
test_types = [TypeType()]

# This chain converts with the variable comparison preserved as a guard.
match override:
    case CallableType() if override.min_args == original.min_args:
        override_kind = "matching callable"
    case Overloaded():
        override_kind = "overloaded"
print(override_kind)

# This chain SHOULD be converted (independent, valid pattern)
for ttype in test_types:
    match ttype:
        case FunctionLike():
            pass
        case TypeType():
            exc_type = ttype.item
        case _:
            pass
print(exc_type)

# assume:

# trace:
# matching callable
# error
