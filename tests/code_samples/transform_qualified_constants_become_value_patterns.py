# before:
class Kind:
    START = 1
    STOP = 2

kind = Kind.START
if kind == Kind.START:
    print("start")
elif kind == Kind.STOP:
    print("stop")
else:
    print("other")

# after:
class Kind:
    START = 1
    STOP = 2

kind = Kind.START
match kind:
    case Kind.START:
        print("start")
    case Kind.STOP:
        print("stop")
    case _:
        print("other")

# assume:

# trace:
# start
