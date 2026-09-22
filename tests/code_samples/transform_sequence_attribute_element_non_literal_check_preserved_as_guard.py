# before:
class Node:
    def __init__(self, y):
        self.y = y

class Point:
    def __init__(self, y):
        self.y = y

value = Node([[0], Point(1)])
if isinstance(value, Node) and len(value.y) == 2 and len(value.y[0]) == 1 and value.y[0][0] == 0 and isinstance(value.y[1], Point) and value.y[1].y == len([None]):
    print("match")
elif isinstance(value, Node):
    print("node")

# after:
class Node:
    def __init__(self, y):
        self.y = y

class Point:
    def __init__(self, y):
        self.y = y

value = Node([[0], Point(1)])
match value:
    case Node(y=[[0], Point()]) if value.y[1].y == len([None]):
        print("match")
    case Node():
        print("node")

# assume:

# trace:
# match
