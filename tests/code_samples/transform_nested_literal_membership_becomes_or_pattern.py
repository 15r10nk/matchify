# before:
class Token:
    def __init__(self, kind):
        self.kind = kind

token = Token("add")
if isinstance(token, Token) and token.kind in ["add", "sub"]:
    print("math")
elif isinstance(token, Token) and token.kind in ["load", "store"]:
    print("memory")

# after:
class Token:
    def __init__(self, kind):
        self.kind = kind

token = Token("add")
match token:
    case Token(kind="add" | "sub"):
        print("math")
    case Token(kind="load" | "store"):
        print("memory")

# assume:

# trace:
# math
