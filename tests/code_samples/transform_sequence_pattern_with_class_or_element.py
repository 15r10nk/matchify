# before:
class Point:
    pass

class Token:
    pass

value = [Point()]
if len(value) == 1 and (isinstance(value[0], Point) or isinstance(value[0], Token)):
    print("point or token")
elif value is None:
    print("none")

# after:
class Point:
    pass

class Token:
    pass

value = [Point()]
match value:
    case Point() | Token(),:
        print("point or token")
    case None:
        print("none")

# assume:

# trace:
# point or token
