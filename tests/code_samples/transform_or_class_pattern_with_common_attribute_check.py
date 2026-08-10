# before:
class A:
    def __init__(self, kind):
        self.kind = kind
class B:
    def __init__(self, kind):
        self.kind = kind

x = A(1)
if (isinstance(x, A) or isinstance(x, B)) and x.kind == 1:
    print("match")
elif isinstance(x, str):
    print("str")

# after:
class A:
    def __init__(self, kind):
        self.kind = kind
class B:
    def __init__(self, kind):
        self.kind = kind

x = A(1)
match x:
    case A(kind=1) | B(kind=1):
        print("match")
    case str():
        print("str")

# assume:

# trace:
# match
