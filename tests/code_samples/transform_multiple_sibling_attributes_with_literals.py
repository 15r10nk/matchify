# before:
class Point:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
p = Point(1, 2, 3)
if isinstance(p, Point) and p.x == 1 and p.y == 2 and p.z == 3:
    print("exact point")
elif isinstance(p, Point):
    print("other point")

# after:
class Point:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
p = Point(1, 2, 3)
match p:
    case Point(x=1, y=2, z=3):
        print("exact point")
    case Point():
        print("other point")

# assume:

# trace:
# exact point
