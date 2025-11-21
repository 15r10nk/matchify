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

# Test case 1: isinstance with tuple of classes on nested attribute
match dec:
    case RefExpr(node=Var() | FuncDef()):
        print("case 1")
    case CallExpr(callee=RefExpr(node=Decorator() | FuncDef() | Var())):
        print("case 2")
