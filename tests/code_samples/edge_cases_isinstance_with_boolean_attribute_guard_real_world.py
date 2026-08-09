# before:
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
print(type(result).__name__)

# after:
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
print(type(result).__name__)

# assume:

# trace:
# AnyType
