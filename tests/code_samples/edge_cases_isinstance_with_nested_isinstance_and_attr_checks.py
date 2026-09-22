# before:
class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    def __init__(self, type=None):
        self.type = type

lv = NameExpr(Var(None))
if isinstance(lv, NameExpr) and isinstance(lv.node, Var) and lv.node.type is None:
    print("match")
elif isinstance(lv, int):
    print("int")

# after:
class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    def __init__(self, type=None):
        self.type = type

lv = NameExpr(Var(None))
match lv:
    case NameExpr(node=Var(type=None)):
        print("match")
    case int():
        print("int")

# assume:

# trace:
# match
