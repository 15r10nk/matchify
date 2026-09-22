# before:
class Point:
    pass

class Data:
    def __init__(self, value):
        self.value = value

obj = Data([Point(), 1, 2])
if isinstance(obj, Data) and len(obj.value) == 3 and isinstance(obj.value[0], Point) and obj.value[1] == 1 and obj.value[2] == 2:
    print("match")
elif isinstance(obj, Data):
    print("other")

# after:
class Point:
    pass

class Data:
    def __init__(self, value):
        self.value = value

obj = Data([Point(), 1, 2])
match obj:
    case Data(value=[Point(), 1, 2]):
        print("match")
    case Data():
        print("other")

# assume:

# trace:
# match
