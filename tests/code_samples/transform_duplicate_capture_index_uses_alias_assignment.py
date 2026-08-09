# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
if isinstance(n, Point) and len(n.x) >= 1:
    first = n.x[0]
    again = n.x[0]
    print(first, again)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
match n:
    case Point(x=[first, *_]):
        again = first
        print(first, again)
    case Point():
        print("empty")

# assume:

# trace:
# 1 1
