# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    def __init__(self, kind):
        self.kind = kind

value = Point(1)
if (isinstance(value, Point) and value.kind > 0) or (isinstance(value, Token) and value.kind > 0):
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    def __init__(self, kind):
        self.kind = kind

value = Point(1)
match value:
    case Point() | Token() if value.kind > 0:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
