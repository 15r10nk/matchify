# before:
class TypeVarTupleType:
    def __repr__(self):
        return "type var tuple"

class ProperType:
    pass

class AnyType(ProperType):
    pass

class UninhabitedType(ProperType):
    pass

t = TypeVarTupleType()
repl = t
if isinstance(repl, TypeVarTupleType):
    result = repl
elif isinstance(repl, ProperType) and isinstance(repl, (AnyType, UninhabitedType)):
    result = "any or uninhabited"
else:
    result = "other"
print(result)

# after:
class TypeVarTupleType:
    def __repr__(self):
        return "type var tuple"

class ProperType:
    pass

class AnyType(ProperType):
    pass

class UninhabitedType(ProperType):
    pass

t = TypeVarTupleType()
repl = t
match repl:
    case TypeVarTupleType():
        result = repl
    case ProperType() if isinstance(repl, (AnyType, UninhabitedType)):
        result = "any or uninhabited"
    case _:
        result = "other"
print(result)

# assume:

# trace:
# type var tuple
