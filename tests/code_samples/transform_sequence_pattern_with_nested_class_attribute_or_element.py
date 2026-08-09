# before:
class Point:
    def __init__(self, node):
        self.node = node

class Node:
    def __init__(self, kind):
        self.kind = kind

class Token:
    pass

value = [Point(Node(1))]
if len(value) == 1 and ((isinstance(value[0], Point) and isinstance(value[0].node, Node) and value[0].node.kind == 1) or isinstance(value[0], Token)):
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, node):
        self.node = node

class Node:
    def __init__(self, kind):
        self.kind = kind

class Token:
    pass

value = [Point(Node(1))]
match value:
    case Point(node=Node(kind=1)) | Token(),:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
