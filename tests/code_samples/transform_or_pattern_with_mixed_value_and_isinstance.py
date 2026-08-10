# before:
class Point:
    pass

value = Point()
if value == 1 or isinstance(value, Point):
    print("one or point")
elif value is None:
    print("none")

# after:
class Point:
    pass

value = Point()
match value:
    case 1 | Point():
        print("one or point")
    case None:
        print("none")

# assume:

# trace:
# one or point
