# before:
class Box:
    def __init__(self, items):
        self.items = items

expected = 1
x = Box([1])
if isinstance(x, Box) and len(x.items) == expected:
    print("guard")
elif isinstance(x, str):
    print("str")

# after:
class Box:
    def __init__(self, items):
        self.items = items

expected = 1
x = Box([1])
match x:
    case Box() if len(x.items) == expected:
        print("guard")
    case str():
        print("str")

# assume:

# trace:
# guard
