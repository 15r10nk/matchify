# before:
class Point:
    pass
class Line:
    pass
node = Point()
if isinstance(node, Point):
    print("point")
elif isinstance(node, Line):
    print("line")
else:
    print("other")

# after:
class Point:
    pass
class Line:
    pass
node = Point()
match node:
    case Point():
        print("point")
    case Line():
        print("line")
    case _:
        print("other")

# assume:

# trace:
# point
