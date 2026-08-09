# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3, 4])
if isinstance(n, Point) and len(n.x) >= 4:
    first = n.x[0]
    third = n.x[2]
    print(first, third)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3, 4])
match n:
    case Point(x=[first, _, third, *_]):
        print(first, third)
    case Point():
        print("empty")

# assume:

# trace:
# 1 3
