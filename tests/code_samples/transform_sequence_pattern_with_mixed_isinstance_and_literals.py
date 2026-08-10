# before:
class Point:
    pass
class Color:
    pass
x = [Point(), Color(), 1]
if len(x) == 3 and isinstance(x[0], Point) and isinstance(x[1], Color) and x[2] == 1:
    print("point, color, 1")
elif len(x) == 3 and x[0] == 0 and x[1] == 0 and x[2] == 0:
    print("zeros")

# after:
class Point:
    pass
class Color:
    pass
x = [Point(), Color(), 1]
match x:
    case Point(), Color(), 1:
        print("point, color, 1")
    case 0, 0, 0:
        print("zeros")

# assume:

# trace:
# point, color, 1
