# before:
class Point:
    pass

class Token:
    pass

class Node:
    pass

node = Node()
node.kind = 1
point = Point()
point.node = node
value = [point]
if len(value) == 1 and isinstance(value[0], (Point, Token)) and hasattr(value[0], "node") and isinstance(value[0].node, Node) and hasattr(value[0].node, "kind") and value[0].node.kind == 1:
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    pass

class Token:
    pass

class Node:
    pass

node = Node()
node.kind = 1
point = Point()
point.node = node
value = [point]
match value:
    case Point(node=Node(kind=1)) | Token(node=Node(kind=1)),:
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
