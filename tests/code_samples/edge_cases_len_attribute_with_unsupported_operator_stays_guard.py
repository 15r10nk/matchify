# before:
class Box:
    def __init__(self, items):
        self.items = items

x = Box([1, 2])
if isinstance(x, Box) and len(x.items) > 1:
    print("guard")
elif isinstance(x, str):
    print("str")

# after:
class Box:
    def __init__(self, items):
        self.items = items

x = Box([1, 2])
match x:
    case Box() if len(x.items) > 1:
        print("guard")
    case str():
        print("str")

# assume:

# trace:
# guard
