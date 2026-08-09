# before:
class Root:
    def __init__(self, left, right):
        self.left = left
        self.right = right

class A:
    pass

class B:
    pass

node = Root(A(), B())
if isinstance(node.left, A) and isinstance(node, Root):
    print("left")
elif isinstance(node.right, B) and isinstance(node, Root):
    print("right")

# after:
class Root:
    def __init__(self, left, right):
        self.left = left
        self.right = right

class A:
    pass

class B:
    pass

node = Root(A(), B())
match node:
    case Root(left=A()):
        print("left")
    case Root(right=B()):
        print("right")

# assume:

# trace:
# left
