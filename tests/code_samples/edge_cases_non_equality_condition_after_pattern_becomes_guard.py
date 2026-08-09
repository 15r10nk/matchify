# before:
class Node:
    pass

node = Node()
if isinstance(node, Node) and node != None:
    print("not none")
elif node is None:
    print("none")

# after:
class Node:
    pass

node = Node()
match node:
    case Node() if node != None:
        print("not none")
    case None:
        print("none")

# assume:

# trace:
# not none
