# before:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(items=[1, None])
if (isinstance(value, Point) and len(value.items) == 2 and value.items[0] == 1 and value.items[1] is None) or value == 0:
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(items=[1, None])
match value:
    case Point(items=[1, None]) | 0:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
