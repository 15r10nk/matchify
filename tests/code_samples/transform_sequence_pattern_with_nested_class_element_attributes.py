# before:
class Point:
    def __init__(self, x):
        self.x = x

class Node:
    def __init__(self, kind):
        self.kind = kind

value = [Point(Node("ready"))]
if len(value) == 1 and isinstance(value[0], Point) and isinstance(value[0].x, Node) and value[0].x.kind == "ready":
    print("match")
elif value == 1:
    print("other")

# after:
class Point:
    def __init__(self, x):
        self.x = x

class Node:
    def __init__(self, kind):
        self.kind = kind

value = [Point(Node("ready"))]
match value:
    case Point(x=Node(kind="ready")),:
        print("match")
    case 1:
        print("other")

# assume:

# trace:
# match
