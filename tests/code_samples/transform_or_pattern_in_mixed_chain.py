# before:
class Point:
    pass
value = 1
if value == 1 or value == 2:
    print("one or two")
elif isinstance(value, Point):
    print("point")
elif value is None:
    print("none")
else:
    print("other")

# after:
class Point:
    pass
value = 1
match value:
    case 1 | 2:
        print("one or two")
    case Point():
        print("point")
    case None:
        print("none")
    case _:
        print("other")

# assume:

# trace:
# one or two
