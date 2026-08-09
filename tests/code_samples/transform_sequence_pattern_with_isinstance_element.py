# before:
class Point:
    pass
x = [Point(), 2]
if len(x) == 2 and isinstance(x[0], Point) and x[1] == 2:
    print("point and 2")
elif len(x) == 2 and x[0] == 1 and x[1] == 1:
    print("1 and 1")
else:
    print("other")

# after:
class Point:
    pass
x = [Point(), 2]
match x:
    case Point(), 2:
        print("point and 2")
    case 1, 1:
        print("1 and 1")
    case _:
        print("other")

# assume:

# trace:
# point and 2
