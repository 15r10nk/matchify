# before:
class Point:
    pass
data = [Point(), 1, 2, 3]
if len(data) >= 2 and isinstance(data[0], Point) and data[1] == 1:
    print("point then 1")
elif len(data) >= 1 and isinstance(data[0], Point):
    print("starts with point")

# after:
class Point:
    pass
data = [Point(), 1, 2, 3]
match data:
    case Point(), 1, *_:
        print("point then 1")
    case Point(), *_:
        print("starts with point")

# assume:

# trace:
# point then 1
