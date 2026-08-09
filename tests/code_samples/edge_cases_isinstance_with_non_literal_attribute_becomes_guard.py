# before:
class Point:
    def __init__(self, x):
        self.x = x

TARGET = 5
obj = Point(5)
if isinstance(obj, Point) and obj.x == TARGET:
    print("match")
elif isinstance(obj, Point):
    print("other")

# after:
class Point:
    def __init__(self, x):
        self.x = x

TARGET = 5
obj = Point(5)
match obj:
    case Point() if obj.x == TARGET:
        print("match")
    case Point():
        print("other")

# assume:

# trace:
# match
