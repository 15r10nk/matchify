# before:
class Outer:
    def __init__(self, child):
        self.child = child

class Point:
    def __init__(self, items):
        self.items = items

class Token:
    def __init__(self, items):
        self.items = items

value = Outer(Point([1, 2]))
if isinstance(value, Outer) and isinstance(value.child, (Point, Token)) and len(value.child.items) >= 2 and value.child.items[1] == 2:
    first = value.child.items[0]
    print(first)
elif value is None:
    print("none")

# after:
class Outer:
    def __init__(self, child):
        self.child = child

class Point:
    def __init__(self, items):
        self.items = items

class Token:
    def __init__(self, items):
        self.items = items

value = Outer(Point([1, 2]))
match value:
    case Outer(child=Point(items=[first, 2, *_]) | Token(items=[first, 2, *_])):
        print(first)
    case None:
        print("none")

# assume:

# trace:
# 1
