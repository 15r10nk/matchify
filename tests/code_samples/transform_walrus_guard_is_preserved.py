# before:
class CallExpr:
    pass

class CallableType:
    pass

def get_type(obj):
    return CallableType()

obj = CallExpr()
if isinstance(obj, CallExpr) and isinstance((call_tp := get_type(obj)), CallableType):
    print("callable")
elif obj is None:
    print("none")

# after:
class CallExpr:
    pass

class CallableType:
    pass

def get_type(obj):
    return CallableType()

obj = CallExpr()
match obj:
    case CallExpr() if isinstance((call_tp := get_type(obj)), CallableType):
        print("callable")
    case None:
        print("none")

# assume:

# trace:
# callable
