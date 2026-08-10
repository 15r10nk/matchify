# before:
OTHER_TYPES = (int,)

class Handler:
    pass

handler = Handler()
value = 1
if isinstance(handler, Handler) and isinstance(value, OTHER_TYPES):
    print("typed handler")
elif handler is None:
    print("none")

# after:
OTHER_TYPES = (int,)

class Handler:
    pass

handler = Handler()
value = 1
match handler:
    case Handler() if isinstance(value, OTHER_TYPES):
        print("typed handler")
    case None:
        print("none")

# assume:

# trace:
# typed handler
