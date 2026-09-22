# before:
class Point:
    def __init__(self, x):
        self.x = x

class Node:
    def __init__(self, x):
        self.x = x

value = Node(1)
if isinstance(value, (Point, Node)) and value.x == 1:
    print("match")
elif isinstance(value, int):
    print("int")

# after:
class Point:
    def __init__(self, x):
        self.x = x

class Node:
    def __init__(self, x):
        self.x = x

value = Node(1)
match value:
    case Point(x=1) | Node(x=1):
        print("match")
    case int():
        print("int")

# assume:

# trace:
# match
