# before:
class Box:
    def __init__(self, kind):
        self.kind = kind

x = Box(1)
if isinstance(x, Box) and hasattr(x, "kind") and x.kind == 1:
    print("one")
elif isinstance(x, str):
    print("str")

# after:
class Box:
    def __init__(self, kind):
        self.kind = kind

x = Box(1)
match x:
    case Box(kind=1):
        print("one")
    case str():
        print("str")

# assume:

# trace:
# one
