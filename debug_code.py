class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    def __init__(self, type=None):
        self.type = type

lv = NameExpr(Var(None))
match lv:
    case NameExpr(node=Var(type=None)):
        print("match - type is None")
    case int():
        print("int")
