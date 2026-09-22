# before:
class Point:
    pass
data = [Point(), "a", 3]
if len(data) == 3 and isinstance(data[0], Point) and data[2] == 3:
    print("point and 3 with gap")
elif len(data) == 3 and isinstance(data[0], Point) and data[2] == 5:
    print("point and 5 with gap")

# after:
class Point:
    pass
data = [Point(), "a", 3]
match data:
    case Point(), _, 3:
        print("point and 3 with gap")
    case Point(), _, 5:
        print("point and 5 with gap")

# assume:

# trace:
# point and 3 with gap
