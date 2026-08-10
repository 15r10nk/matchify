# before:
class Data:
    def __init__(self, value):
        self.value = value

obj = Data([1, 2, 3])
if isinstance(obj, Data) and isinstance(obj.value, (list, tuple)) and len(obj.value) >= 1:
    first = obj.value[0]
    print(first)
elif isinstance(obj, Data):
    print("other data")

# after:
class Data:
    def __init__(self, value):
        self.value = value

obj = Data([1, 2, 3])
match obj:
    case Data(value=[first, *_]) if isinstance(obj.value, (list, tuple)):
        print(first)
    case Data():
        print("other data")

# assume:

# trace:
# 1
