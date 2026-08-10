# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

value = Point(1)
if value == "ready" or (isinstance(value, Point) and value.kind == 1):
    print("ready or point")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, kind):
        self.kind = kind

value = Point(1)
match value:
    case "ready" | Point(kind=1):
        print("ready or point")
    case None:
        print("none")

# assume:

# trace:
# ready or point
