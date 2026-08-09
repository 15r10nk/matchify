# before:
class Node:
    pass

if isinstance((node := Node()), Node):
    print("node")
elif isinstance(node, int):
    print("int")

# after:
class Node:
    pass

if isinstance((node := Node()), Node):
    print("node")
elif isinstance(node, int):
    print("int")

# assume:

# trace:
# node
