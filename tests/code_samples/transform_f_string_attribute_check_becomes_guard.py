# before:
class Point:
    def __init__(self, x):
        self.x = x
value = Point(f"ready")
if isinstance(value, Point) and value.x == f"ready":
    print("ready")
elif isinstance(value, Point):
    print("point")

# after:
class Point:
    def __init__(self, x):
        self.x = x
value = Point(f"ready")
match value:
    case Point() if value.x == f"ready":
        print("ready")
    case Point():
        print("point")

# assume:

# trace:
# ready
