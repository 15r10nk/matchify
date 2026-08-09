# before:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(x=Node(kind=1))
if (isinstance(value, Point) and hasattr(value, "x") and isinstance(value.x, Node) and hasattr(value.x, "kind") and value.x.kind == 1) or value == 0:
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(x=Node(kind=1))
match value:
    case Point(x=Node(kind=1)) | 0:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
