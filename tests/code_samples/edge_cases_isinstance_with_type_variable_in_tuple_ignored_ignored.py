# before:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_FUNCBASE_TYPES = (FuncDef, OverloadedFuncDef)

class Var:
    pass

node = Var()
if isinstance(node, (Var, SYMBOL_FUNCBASE_TYPES)):
    print("match")
elif isinstance(node, int):
    print("int")

# after:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_FUNCBASE_TYPES = (FuncDef, OverloadedFuncDef)

class Var:
    pass

node = Var()
if isinstance(node, (Var, SYMBOL_FUNCBASE_TYPES)):
    print("match")
elif isinstance(node, int):
    print("int")

# assume:
# ignore-types: .*_TYPES$

# trace:
# match
