# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    pass

value = Point(1)
if (isinstance(value, Point) and value.kind > 0) or isinstance(value, Token):
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
    case _ if (isinstance(value, Point) and value.kind > 0) or isinstance(value, Token):
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
