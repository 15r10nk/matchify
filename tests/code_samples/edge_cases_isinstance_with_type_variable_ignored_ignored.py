# before:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_TYPES = (FuncDef, OverloadedFuncDef)

n = FuncDef()
if isinstance(n, SYMBOL_TYPES):
    print("match")
elif isinstance(n, int):
    print("int")

# after:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_TYPES = (FuncDef, OverloadedFuncDef)

n = FuncDef()
if isinstance(n, SYMBOL_TYPES):
    print("match")
elif isinstance(n, int):
    print("int")

# assume:
# ignore-types: .*_TYPES$

# trace:
# match
