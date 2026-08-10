# before:
class Point:
    pass
class Line:
    pass
x = [Point(), 1]
if len(x) == 2 and isinstance(x[0], (Point, Line)) and x[1] == 1:
    print("point or line and 1")
elif len(x) == 2 and x[0] == 0 and x[1] == 0:
    print("0 and 0")

# after:
class Point:
    pass
class Line:
    pass
x = [Point(), 1]
match x:
    case Point() | Line(), 1:
        print("point or line and 1")
    case 0, 0:
        print("0 and 0")

# assume:

# trace:
# point or line and 1
