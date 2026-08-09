# before:
class Point:
    def __init__(self, x):
        self.x = x

value = Point([[1, 2]])
if isinstance(value, Point) and len(value.x) == 1 and len(value.x[0]) == 2 and value.x[0][0] == 1 and value.x[0][1] == 2:
    print("match")
elif isinstance(value, Point):
    print("other")

# after:
class Point:
    def __init__(self, x):
        self.x = x

value = Point([[1, 2]])
match value:
    case Point(x=[[1, 2]]):
        print("match")
    case Point():
        print("other")

# assume:

# trace:
# match
