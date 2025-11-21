class Decorator:
    pass

class Handler:
    pass

item = Decorator()

# Comment before if
match item:
    case Decorator():
        print("decorator")
    # Comment before elif
    case Handler():
        print("handler")
    # Comment before else
    case _:
        print("something else")
