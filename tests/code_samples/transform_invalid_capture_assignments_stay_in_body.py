# before:
class A:
    def __init__(self, x):
        self.x = x
class B:
    def __init__(self, x):
        self.x = x
class C:
    def __init__(self, x):
        self.x = x
class D:
    def __init__(self, x):
        self.x = x
class E:
    def __init__(self, x):
        self.x = x

other_items = [30]
i = 0
for n in (A([1]), B([2]), C([3]), D([4]), E([5])):
    print(type(n).__name__)
    if isinstance(n, A) and len(n.x) >= 1:
        first = second = n.x[0]
        print(first, second)
    elif isinstance(n, B) and len(n.x) >= 1:
        n.value = n.x[0]
        print(n.value)
    elif isinstance(n, C) and len(n.x) >= 1:
        value = other_items[0]
        print(value)
    elif isinstance(n, D) and len(n.x) >= 1:
        value = n.x[0:1]
        print(value)
    elif isinstance(n, E) and len(n.x) >= 1:
        value = n.x[i]
        print(value)

# after:
class A:
    def __init__(self, x):
        self.x = x
class B:
    def __init__(self, x):
        self.x = x
class C:
    def __init__(self, x):
        self.x = x
class D:
    def __init__(self, x):
        self.x = x
class E:
    def __init__(self, x):
        self.x = x

other_items = [30]
i = 0
for n in (A([1]), B([2]), C([3]), D([4]), E([5])):
    print(type(n).__name__)
    match n:
        case A(x=[_, *_]):
            first = second = n.x[0]
            print(first, second)
        case B(x=[_, *_]):
            n.value = n.x[0]
            print(n.value)
        case C(x=[_, *_]):
            value = other_items[0]
            print(value)
        case D(x=[_, *_]):
            value = n.x[0:1]
            print(value)
        case E(x=[_, *_]):
            value = n.x[i]
            print(value)

# assume:

# trace:
# A
# 1 1
# B
# 2
# C
# 30
# D
# [4]
# E
# 5
