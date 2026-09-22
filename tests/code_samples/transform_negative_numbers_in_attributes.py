# before:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
p = Point(-5, 10)
if isinstance(p, Point) and p.x == -5:
    print("x is -5")
elif isinstance(p, Point) and p.y == 10:
    print("y is 10")

# after:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
p = Point(-5, 10)
match p:
    case Point(x=-5):
        print("x is -5")
    case Point(y=10):
        print("y is 10")

# assume:

# trace:
# x is -5
