# before:
class TupleType:
    is_valid = True

item = TupleType()
if isinstance(item, TupleType) and item.is_valid:
    print("valid tuple")
elif isinstance(item, int):
    print("int")

# after:
class TupleType:
    is_valid = True

item = TupleType()
match item:
    case TupleType() if item.is_valid:
        print("valid tuple")
    case int():
        print("int")

# assume:

# trace:
# valid tuple
