# before:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
value = [Point(1, 2)]
if len(value) == 1 and isinstance(value[0], Point) and value[0].x == 1 and value[0].y == 2:
    print("match")
elif value == 1:
    print("other")

# after:
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
value = [Point(1, 2)]
match value:
    case Point(x=1, y=2),:
        print("match")
    case 1:
        print("other")

# assume:

# trace:
# match
