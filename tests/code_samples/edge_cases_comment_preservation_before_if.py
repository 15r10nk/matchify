# before:
class Decorator:
    pass

item = Decorator()

# TODO: support decorated overloaded functions properly
if isinstance(item, Decorator):
    print("decorator")
elif isinstance(item, int):
    print("int")

# after:
class Decorator:
    pass

item = Decorator()

# TODO: support decorated overloaded functions properly
match item:
    case Decorator():
        print("decorator")
    case int():
        print("int")

# assume:

# trace:
# decorator
