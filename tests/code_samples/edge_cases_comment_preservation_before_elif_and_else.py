# before:
class Decorator:
    pass

class Handler:
    pass

item = Decorator()

# Comment before if
if isinstance(item, Decorator):
    print("decorator")
# Comment before elif
elif isinstance(item, Handler):
    print("handler")
# Comment before else
else:
    print("other")

# after:
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
        print("other")

# assume:

# trace:
# decorator
