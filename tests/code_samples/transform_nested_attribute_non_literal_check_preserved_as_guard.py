# before:
class Point:
    pass

value = Point()
value.x = Point()
value.x.x = Point()
value.x.x.y = "ready"
if isinstance(value, Point) and isinstance(value.x, Point) and isinstance(value.x.x, Point) and value.x.x.y == str("ready"):
    print("match")
elif isinstance(value, Point):
    print("other")

# after:
class Point:
    pass

value = Point()
value.x = Point()
value.x.x = Point()
value.x.x.y = "ready"
match value:
    case Point(x=Point(x=Point())) if value.x.x.y == str("ready"):
        print("match")
    case Point():
        print("other")

# assume:

# trace:
# match
