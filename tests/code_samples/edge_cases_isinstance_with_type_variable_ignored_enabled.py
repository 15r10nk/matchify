# before:
class FuncDef:
    pass

class OverloadedFuncDef:
    pass

SYMBOL_TYPES = FuncDef

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

SYMBOL_TYPES = FuncDef

n = FuncDef()
match n:
    case SYMBOL_TYPES():
        print("match")
    case int():
        print("int")

# assume:

# trace:
# match
