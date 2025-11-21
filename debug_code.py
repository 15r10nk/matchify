class Decorator:
    pass

item = Decorator()

# TODO: support decorated overloaded functions properly
match item:
    case Decorator():
        print("decorator")
    case int():
        print("int")
