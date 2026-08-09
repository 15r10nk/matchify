# before:
class Node:
    pass

class Token:
    def __init__(self, x, y):
        self.x = x
        self.y = y

value = Node()
value.kind = [Node(), True]
value.y = Token('ready', 0)
if isinstance(value, Node) and len(value.kind) == 2 and isinstance(value.kind[0], Node) and value.kind[1] is True and isinstance(value.y, Token) and value.y.x == 'ready' and value.y.y == 0:
    print("match")
elif isinstance(value, Node):
    print("other")

# after:
class Node:
    pass

class Token:
    def __init__(self, x, y):
        self.x = x
        self.y = y

value = Node()
value.kind = [Node(), True]
value.y = Token('ready', 0)
match value:
    case Node(kind=[Node(), True], y=Token(x='ready', y=0)):
        print("match")
    case Node():
        print("other")

# assume:

# trace:
# match
