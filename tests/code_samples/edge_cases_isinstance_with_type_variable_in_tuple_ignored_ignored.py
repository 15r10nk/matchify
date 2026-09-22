# before:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_FUNCBASE_TYPES = (FuncDef, OverloadedFuncDef)

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

SYMBOL_FUNCBASE_TYPES = (FuncDef, OverloadedFuncDef)

class Var:
    pass

for node in (Var(), FuncDef(), OverloadedFuncDef(), 42, object()):
    if isinstance(node, (Var, SYMBOL_FUNCBASE_TYPES)):
        print("match")
    elif isinstance(node, int):
        print("int")
    else:
        print("other")

# assume:
# ignore-types: .*_TYPES$

# trace:
# match
# match
# match
# int
# other
