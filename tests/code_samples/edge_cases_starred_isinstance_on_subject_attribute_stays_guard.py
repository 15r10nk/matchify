# before:
types = (str,)
class Box:
    def __init__(self, item):
        self.item = item

x = Box("ok")
if isinstance(x, Box) and isinstance(x.item, (*types,)):
    print("guard")
elif isinstance(x, str):
    print("str")

# after:
types = (str,)
class Box:
    def __init__(self, item):
        self.item = item

x = Box("ok")
match x:
    case Box() if isinstance(x.item, (*types,)):
        print("guard")
    case str():
        print("str")

# assume:

# trace:
# guard
