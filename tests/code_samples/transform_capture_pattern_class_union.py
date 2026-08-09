# before:
class Point:
    def __init__(self, x):
        self.x = x

class Token:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
if isinstance(n, (Point, Token)) and len(n.x) >= 1:
    item = n.x[0]
    print(item)
elif isinstance(n, int):
    print("int")

# after:
class Point:
    def __init__(self, x):
        self.x = x

class Token:
    def __init__(self, x):
        self.x = x

n = Point([1, 2, 3])
match n:
    case Point(x=[item, *_]) | Token(x=[item, *_]):
        print(item)
    case int():
        print("int")

# assume:

# trace:
# 1
