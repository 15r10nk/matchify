# before:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
node = Point(None, 10)
if isinstance(node, Point) and node.x is None:
    print("x is none")
elif isinstance(node, Point) and node.x == 5:
    print("x is 5")
else:
    print("other")

# after:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
node = Point(None, 10)
match node:
    case Point(x=None):
        print("x is none")
    case Point(x=5):
        print("x is 5")
    case _:
        print("other")

# assume:

# trace:
# x is none
