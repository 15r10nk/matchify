# before:
class Point:
    pass
class Container:
    def __init__(self, inner):
        self.inner = inner
x = [Container(Point()), 5]
if len(x) == 2 and isinstance(x[0], Container) and x[1] == 5:
    print("sequence with container")
elif len(x) == 2 and x[0] == 1 and x[1] == 1:
    print("ones")

# after:
class Point:
    pass
class Container:
    def __init__(self, inner):
        self.inner = inner
x = [Container(Point()), 5]
match x:
    case Container(), 5:
        print("sequence with container")
    case 1, 1:
        print("ones")

# assume:

# trace:
# sequence with container
