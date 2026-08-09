# before:
class Point:
    def __init__(self, data):
        self.data = data

class Data:
    def __init__(self, items):
        self.items = items

n = Point(Data([1, 2, 3]))
if isinstance(n, Point) and isinstance(n.data, Data) and len(n.data.items) >= 1:
    item = n.data.items[0]
    print(item)
elif isinstance(n, Point):
    print("point")

# after:
class Point:
    def __init__(self, data):
        self.data = data

class Data:
    def __init__(self, items):
        self.items = items

n = Point(Data([1, 2, 3]))
match n:
    case Point(data=Data(items=[item, *_])):
        print(item)
    case Point():
        print("point")

# assume:

# trace:
# 1
