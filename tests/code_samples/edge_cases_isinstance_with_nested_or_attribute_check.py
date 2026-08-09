# before:
class Point:
    def __init__(self, data=None):
        self.data = data

class Data:
    def __init__(self, kind=None):
        self.kind = kind

obj = Point(Data(2))
if isinstance(obj, Point) and isinstance(obj.data, Data) and (obj.data.kind == 1 or obj.data.kind == 2):
    print("match")
elif isinstance(obj, int):
    print("int")

# after:
class Point:
    def __init__(self, data=None):
        self.data = data

class Data:
    def __init__(self, kind=None):
        self.kind = kind

obj = Point(Data(2))
match obj:
    case Point(data=Data(kind=1 | 2)):
        print("match")
    case int():
        print("int")

# assume:

# trace:
# match
