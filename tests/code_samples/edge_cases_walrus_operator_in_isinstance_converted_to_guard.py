# before:
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

# after:
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

# assume:

# trace:
# matched
