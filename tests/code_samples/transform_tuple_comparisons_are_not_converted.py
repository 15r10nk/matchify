# before:
class Box:
    def __init__(self, x=None, y=None):
        self.x = x
        self.y = y

a = Box(x=1)
b = Box(y=2)
if (a.x, b.y) == (1, 2):
    print("first")
elif (a.x, b.y) == (3, 4):
    print("second")

# after:
class Box:
    def __init__(self, x=None, y=None):
        self.x = x
        self.y = y

a = Box(x=1)
b = Box(y=2)
if (a.x, b.y) == (1, 2):
    print("first")
elif (a.x, b.y) == (3, 4):
    print("second")

# assume:

# trace:
# first
