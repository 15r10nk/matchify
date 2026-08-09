# before:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1])
if isinstance(n, Point) and len(n.x) >= 1:
    value = n.x[0]
elif isinstance(n, Point):
    print("empty")
print(value)

# after:
class Point:
    def __init__(self, x):
        self.x = x

n = Point([1])
match n:
    case Point(x=[value, *_]):
        pass
    case Point():
        print("empty")
print(value)

# assume:

# trace:
# 1
