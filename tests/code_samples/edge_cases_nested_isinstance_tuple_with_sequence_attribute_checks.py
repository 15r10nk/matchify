# before:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(x=Node(x=[False], kind=True))
if isinstance(value, (Point, Token)) and isinstance(value.x, (Node, Point)) and len(value.x.x) == 1 and value.x.x[0] is False and value.x.kind is True:
    print("match")
elif value == 0:
    print("zero")

# after:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Node:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(x=Node(x=[False], kind=True))
match value:
    case Point(x=Node(x=[False], kind=True) | Point(x=[False], kind=True)) | Token(x=Node(x=[False], kind=True) | Point(x=[False], kind=True)):
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
