# before:
class Point:
    pass

value = [Point()]
if len(value) == 1 and (value[0] == 1 or isinstance(value[0], Point)):
    print("one or point")
elif value is None:
    print("none")

# after:
class Point:
    pass

value = [Point()]
match value:
    case 1 | Point(),:
        print("one or point")
    case None:
        print("none")

# assume:

# trace:
# one or point
