# before:
class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    def __init__(self, type=None):
        self.type = type

class PartialType:
    pass

lvalue = NameExpr(Var(PartialType()))
if isinstance(lvalue, NameExpr) and isinstance(lvalue.node, Var) and isinstance(lvalue.node.type, PartialType):
    print("match")
elif isinstance(lvalue, int):
    print("int")

# after:
class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    def __init__(self, type=None):
        self.type = type

class PartialType:
    pass

lvalue = NameExpr(Var(PartialType()))
match lvalue:
    case NameExpr(node=Var(type=PartialType())):
        print("match")
    case int():
        print("int")

# assume:

# trace:
# match
