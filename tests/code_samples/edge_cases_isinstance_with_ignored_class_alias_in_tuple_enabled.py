# before:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_FUNCBASE_TYPES = FuncDef

class Var:
    pass

for node in (Var(), FuncDef(), OverloadedFuncDef(), 42, object()):
    if isinstance(node, (Var, SYMBOL_FUNCBASE_TYPES)):
        print("match")
    elif isinstance(node, int):
        print("int")
    else:
        print("other")

# after:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_FUNCBASE_TYPES = FuncDef

class Var:
    pass

for node in (Var(), FuncDef(), OverloadedFuncDef(), 42, object()):
    match node:
        case Var() | SYMBOL_FUNCBASE_TYPES():
            print("match")
        case int():
            print("int")
        case _:
            print("other")

# assume:

# trace:
# match
# match
# other
# int
# other
