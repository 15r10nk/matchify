# before:
class Point:
    def __init__(self, x):
        self.x = x

value = Point(2)
if isinstance(value, Point) and (value.x == 1 or value.x == 2):
    print("match")
elif isinstance(value, Point):
    print("other")

# after:
class Point:
    def __init__(self, x):
        self.x = x

value = Point(2)
match value:
    case Point(x=1 | 2):
        print("match")
    case Point():
        print("other")

# assume:

# trace:
# match
