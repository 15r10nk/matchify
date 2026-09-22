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
if kind is Kind.START:
    print("start")
elif kind is Kind.STOP:
    print("stop")
else:
    print("other")

# assume:
# ignore-types: .*_TYPES$

# trace:
# start
