# before:
class Point:
    def __init__(self, x):
        self.x = x

class Node:
    def __init__(self, x):
        self.x = x

value = [Node(1)]
if len(value) == 1 and isinstance(value[0], (Point, Node)) and value[0].x == 1:
    print("match")
elif value == 0:
    print("zero")

# after:
class Point:
    def __init__(self, x):
        self.x = x

class Node:
    def __init__(self, x):
        self.x = x

value = [Node(1)]
match value:
    case Point(x=1) | Node(x=1),:
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
