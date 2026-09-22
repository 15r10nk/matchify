# before:
class Box:
    def __init__(self, x=None, y=None):
        self.x = x
        self.y = y

a = Box(x=1)
b = Box(y=2)
if a.x == 1 and b.y == 2:
    print("first")
elif a.x == 3 and b.y == 4:
    print("second")

# after:
class Box:
    def __init__(self, x=None, y=None):
        self.x = x
        self.y = y

a = Box(x=1)
b = Box(y=2)
match (a.x, b.y):
    case 1, 2:
        print("first")
    case 3, 4:
        print("second")

# assume: pure-subjects
# ignore-types: .*_TYPES$

# trace:
# first
