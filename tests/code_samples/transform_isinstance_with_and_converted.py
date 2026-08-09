# before:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
node = Point(5, 10)
if isinstance(node, Point) and node.x == 5:
    print("point at x=5")
elif isinstance(node, Point):
    print("other point")

# after:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
node = Point(5, 10)
match node:
    case Point(x=5):
        print("point at x=5")
    case Point():
        print("other point")

# assume:

# trace:
# point at x=5
