# before:
class Point:
    def __init__(self, kind):
        self.kind = kind

value = [None, Point(3), True]
if len(value) >= 3 and isinstance(value[1], Point) and hasattr(value[1], "kind") and value[1].kind == 3 and value[2] is True or value == 0:
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, kind):
        self.kind = kind

value = [None, Point(3), True]
match value:
    case [_, Point(kind=3), True, *_] | 0:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
