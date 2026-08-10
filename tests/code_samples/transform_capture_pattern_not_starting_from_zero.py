# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3, 4])
if isinstance(n, Point) and len(n.x) >= 4:
    second = n.x[1]
    third = n.x[2]
    print(second, third)
elif isinstance(n, Point):
    print("empty")

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3, 4])
match n:
    case Point(x=[_, second, third, *_]):
        print(second, third)
    case Point():
        print("empty")

# assume:

# trace:
# 2 3
