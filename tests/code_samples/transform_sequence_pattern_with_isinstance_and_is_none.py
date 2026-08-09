# before:
class Point:
    pass
x = [Point(), None]
if len(x) == 2 and isinstance(x[0], Point) and x[1] is None:
    print("point and none")
elif len(x) == 2 and x[0] == 1 and x[1] == 2:
    print("1 and 2")

# after:
class Point:
    pass
x = [Point(), None]
match x:
    case Point(), None:
        print("point and none")
    case 1, 2:
        print("1 and 2")

# assume:

# trace:
# point and none
