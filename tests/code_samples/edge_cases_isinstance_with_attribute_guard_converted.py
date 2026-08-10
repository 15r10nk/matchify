# before:
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
actual_type.args.append("argument")
if isinstance(actual_type, Instance) and actual_type.args:
    result = "instance with args"
elif isinstance(actual_type, TupleType):
    result = "tuple"
elif isinstance(actual_type, ParamSpecType):
    result = "paramspec"
else:
    result = "other"
print(result)

# after:
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
actual_type.args.append("argument")
match actual_type:
    case Instance() if actual_type.args:
        result = "instance with args"
    case TupleType():
        result = "tuple"
    case ParamSpecType():
        result = "paramspec"
    case _:
        result = "other"
print(result)

# assume:

# trace:
# instance with args
