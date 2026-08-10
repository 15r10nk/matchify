# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    def __init__(self, kind):
        self.kind = kind

value = [Point(1)]
if len(value) == 1 and ((isinstance(value[0], Point) and value[0].kind == 1) or (isinstance(value[0], Token) and value[0].kind == 2)):
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

value = [Point(1)]
match value:
    case Point(kind=1) | Token(kind=2),:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
