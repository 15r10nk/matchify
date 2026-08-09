# before:
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

# after:
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

# assume:

# trace:
# matched
