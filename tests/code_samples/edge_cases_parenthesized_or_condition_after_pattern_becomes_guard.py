# before:
ready = False
forced = True

class Handler:
    pass

handler = Handler()
if isinstance(handler, Handler) and (ready or forced):
    print("go")
elif handler is None:
    print("none")

# after:
ready = False
forced = True

class Handler:
    pass

handler = Handler()
match handler:
    case Handler() if (ready or forced):
        print("go")
    case None:
        print("none")

# assume:

# trace:
# go
