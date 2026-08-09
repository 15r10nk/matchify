# before:
class Data:
    def __init__(self, value):
        self.value = value

obj = Data([1, 2, 3])
if isinstance(obj, Data) and len(obj.value) == 3 and obj.value[0] == 1 and obj.value[1] == 2 and obj.value[2] == 3:
    print("match")
elif isinstance(obj, Data):
    print("other data")

# after:
class Data:
    def __init__(self, value):
        self.value = value

obj = Data([1, 2, 3])
match obj:
    case Data(value=[1, 2, 3]):
        print("match")
    case Data():
        print("other data")

# assume:

# trace:
# match
