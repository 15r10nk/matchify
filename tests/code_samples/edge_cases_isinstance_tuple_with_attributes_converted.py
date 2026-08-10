# before:
class Point:
    def __init__(self, x):
        self.x = x
class Line:
    def __init__(self, x):
        self.x = x

for obj in (Point(5), Line(5), Point(4), 0):
    if isinstance(obj, (Point, Line)) and obj.x == 5:
        print("match")
    elif obj == 0:
        print("zero")

# after:
class Point:
    def __init__(self, x):
        self.x = x
class Line:
    def __init__(self, x):
        self.x = x

for obj in (Point(5), Line(5), Point(4), 0):
    match obj:
        case Point(x=5) | Line(x=5):
            print("match")
        case 0:
            print("zero")

# assume:

# trace:
# match
# match
# zero
