# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    pass

value = Point(1)
if (isinstance(value, Point) and hasattr(value, "kind") and value.kind == 1) or isinstance(value, Token):
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    pass

value = Point(1)
match value:
    case Point(kind=1) | Token():
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
