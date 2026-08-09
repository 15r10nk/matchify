# before:
class TupleType: pass
class Types: pass
types = Types()
types.TupleType = TupleType
value = [1]

if isinstance(value, (list, types.TupleType)) and len(value) == 1:
    result = "one"
elif value is None:
    result = "none"
print(result)

# after:
class TupleType: pass
class Types: pass
types = Types()
types.TupleType = TupleType
value = [1]

match value:
    case _ if isinstance(value, (list, types.TupleType)) and len(value) == 1:
        result = "one"
    case None:
        result = "none"
print(result)

# assume: list-sequence-pattern,tuple-sequence-pattern

# trace:
# one
