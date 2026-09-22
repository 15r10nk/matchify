# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    def __init__(self, x):
        self.x = x

value = [Point(Token(2))]
if len(value) >= 1 and isinstance(value[0], Point) and isinstance(value[0].kind, Token) and value[0].kind.x == len([None, None]):
    print("match")
elif len(value) >= 1 and isinstance(value[0], Point):
    print("point")

# after:
class Point:
    def __init__(self, kind):
        self.kind = kind

class Token:
    def __init__(self, x):
        self.x = x

value = [Point(Token(2))]
match value:
    case Point(kind=Token()), *_ if value[0].kind.x == len([None, None]):
        print("match")
    case Point(), *_:
        print("point")

# assume:

# trace:
# match
