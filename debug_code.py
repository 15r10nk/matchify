class NameExpr:
    def __init__(self, node=None):
        self.node = node

class Var:
    def __init__(self, type=None):
        self.type = type

class PartialType:
    pass

class MemberExpr:
    pass

lvalue = NameExpr(Var(PartialType()))
match lvalue:
    case NameExpr(node=Var(type=PartialType())):
        var = lvalue.node
        print("NameExpr with Var with PartialType")
    case MemberExpr():
        var = "member"
        print("MemberExpr")
    case _:
        var = None
        print("other")
