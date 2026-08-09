# before:
class Point:
    def __init__(self, data=None):
        self.data = data

class Data:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

objects = [
    Point(Data(5, 10)),
    Point(Data(5, 9)),
    Point(None),
    7,
]
for obj in objects:
    if isinstance(obj, Point) and isinstance(obj.data, Data) and obj.data.x == 5 and obj.data.y == 10:
        print("match")
    elif isinstance(obj, int):
        print("int")
    else:
        print("no match")

# after:
class Point:
    def __init__(self, data=None):
        self.data = data

class Data:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

objects = [
    Point(Data(5, 10)),
    Point(Data(5, 9)),
    Point(None),
    7,
]
for obj in objects:
    match obj:
        case Point(data=Data(x=5, y=10)):
            print("match")
        case int():
            print("int")
        case _:
            print("no match")

# assume:

# trace:
# match
# no match
# no match
# int
