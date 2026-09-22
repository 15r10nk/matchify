# before:
class Point:
    pass

z = [Point(), [1, 2]]
if len(z) == 2 and isinstance(z[0], Point) and len(z[1]) == 2 and z[1][0] == 1 and z[1][1] == 2:
    print("match")
elif z == 0:
    print("zero")

# after:
class Point:
    pass

z = [Point(), [1, 2]]
match z:
    case Point(), [1, 2]:
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
