# before:
class Point:
    def __init__(self, data=None):
        self.data = data

class Data:
    def __init__(self, kind=None):
        self.kind = kind

objects = [
    Point(Data([1, 2])),
    Point(Data((1, 2))),
    Point(Data([1, 3])),
    7,
]
for obj in objects:
    if isinstance(obj, Point) and isinstance(obj.data, Data) and len(obj.data.kind) == 2 and obj.data.kind[0] == 1 and obj.data.kind[1] == 2:
        print("nested sequence")
    elif isinstance(obj, int):
        print("integer")
    else:
        print("no match")

# after:
class Point:
    def __init__(self, data=None):
        self.data = data

class Data:
    def __init__(self, kind=None):
        self.kind = kind

objects = [
    Point(Data([1, 2])),
    Point(Data((1, 2))),
    Point(Data([1, 3])),
    7,
]
for obj in objects:
    match obj:
        case Point(data=Data(kind=[1, 2])):
            print("nested sequence")
        case int():
            print("integer")
        case _:
            print("no match")

# assume:

# trace:
# nested sequence
# nested sequence
# no match
# integer
