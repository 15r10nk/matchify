# before:
class Value: pass
class TupleType:
    partial_fallback = Value()
TupleType.partial_fallback.type = Value()
TupleType.partial_fallback.type.is_named_tuple = True

item = TupleType()
if isinstance(item, TupleType) and item.partial_fallback.type.is_named_tuple:
    print("named tuple")
elif isinstance(item, int):
    print("int")

# after:
class Value: pass
class TupleType:
    partial_fallback = Value()
TupleType.partial_fallback.type = Value()
TupleType.partial_fallback.type.is_named_tuple = True

item = TupleType()
match item:
    case TupleType() if item.partial_fallback.type.is_named_tuple:
        print("named tuple")
    case int():
        print("int")

# assume:

# trace:
# named tuple
