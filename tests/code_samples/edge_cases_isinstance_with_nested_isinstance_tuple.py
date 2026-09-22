# before:
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

# after:
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

# assume:

# trace:
# case 1
