# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
if isinstance(n, Point) and len(n.x) >= 1:
    value = n.x[0]
    print(value)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
match n:
    case Point(x=[value, *_]):
        print(value)
    case Point():
        print("empty")

# assume:

# trace:
# 1
