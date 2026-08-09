# before:
class Point:
    def __init__(self, kind=None, y=None):
        self.kind = kind
        self.y = y

class Token:
    pass

value = Point(kind=[object(), ["ready", False, False], Token()], y=Point(kind=1))
if isinstance(value, Point) and len(value.kind) >= 3 and len(value.kind[1]) >= 3 and value.kind[1][0] == "ready" and value.kind[1][1] is False and value.kind[1][2] is False and isinstance(value.kind[2], Token) and isinstance(value.y, Point) and value.y.kind > 0:
    print("match")
elif isinstance(value, Point):
    print("point")

# after:
class Point:
    def __init__(self, kind=None, y=None):
        self.kind = kind
        self.y = y

class Token:
    pass

value = Point(kind=[object(), ["ready", False, False], Token()], y=Point(kind=1))
match value:
    case Point(kind=[_, ["ready", False, False, *_], Token(), *_], y=Point()) if value.y.kind > 0:
        print("match")
    case Point():
        print("point")

# assume:

# trace:
# match
