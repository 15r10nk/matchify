# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1])
if isinstance(n, Point) and len(n.x) >= 1:
    first = n.x[0]
    again = n.x[0]
elif isinstance(n, Point):
    print("empty")
print(first, again)

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1])
match n:
    case Point(x=[first, *_]):
        again = first
    case Point():
        print("empty")
print(first, again)

# assume:

# trace:
# 1 1
