# before:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

n = Point([1, 2], [3, 4])
if isinstance(n, Point) and len(n.x) >= 1 and len(n.y) >= 1:
    x_val = n.x[0]
    y_val = n.y[0]
    print(x_val, y_val)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

n = Point([1, 2], [3, 4])
match n:
    case Point(x=[x_val, *_], y=[y_val, *_]):
        print(x_val, y_val)
    case Point():
        print("empty")

# assume:

# trace:
# 1 3
