# before:
class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    pass

lvalue = NameExpr(Var())
if isinstance(lvalue, NameExpr) and isinstance(lvalue.node, Var):
    print("match")
elif isinstance(lvalue, int):
    print("int")

# after:
class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    pass

lvalue = NameExpr(Var())
match lvalue:
    case NameExpr(node=Var()):
        print("match")
    case int():
        print("int")

# assume:

# trace:
# match
