# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
if isinstance(n, Point) and len(n.x) >= 2:
    first = n.x[0]
    second = n.x[1]
    print(first, second)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
match n:
    case Point(x=[first, second, *_]):
        print(first, second)
    case Point():
        print("empty")

# assume:

# trace:
# 1 2
