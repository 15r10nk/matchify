# before:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

n = Point([1, 2, 3], [4, 5, 6])
if isinstance(n, Point) and len(n.x) >= 2 and len(n.y) >= 2:
    x1 = n.x[0]
    x2 = n.x[1]
    y1 = n.y[0]
    y2 = n.y[1]
    print(x1, x2, y1, y2)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

n = Point([1, 2, 3], [4, 5, 6])
match n:
    case Point(x=[x1, x2, *_], y=[y1, y2, *_]):
        print(x1, x2, y1, y2)
    case Point():
        print("empty")

# assume:

# trace:
# 1 2 4 5
