# before:
class Kind:
    START = object()
    STOP = object()

kind = Kind.START
if kind is Kind.START:
    print("start")
elif kind is Kind.STOP:
    print("stop")
else:
    print("other")

# after:
class Kind:
    START = object()
    STOP = object()

kind = Kind.START
match kind:
    case Kind.START:
        print("start")
    case Kind.STOP:
        print("stop")
    case _:
        print("other")

# assume: identity-equality
# ignore-types: .*_TYPES$

# trace:
# start
