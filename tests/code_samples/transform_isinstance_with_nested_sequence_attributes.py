# before:
class Data:
    def __init__(self, value):
        self.value = value

inner = Data([1, 2, 3])
outer = Data([inner])
if isinstance(outer, Data) and len(outer.value) == 1 and isinstance(outer.value[0], Data) and len(outer.value[0].value) == 3 and outer.value[0].value[0] == 1 and outer.value[0].value[1] == 2 and outer.value[0].value[2] == 3:
    print("match")
elif isinstance(outer, Data):
    print("other")

# after:
class Data:
    def __init__(self, value):
        self.value = value

inner = Data([1, 2, 3])
outer = Data([inner])
match outer:
    case Data(value=[Data(value=[1, 2, 3])]):
        print("match")
    case Data():
        print("other")

# assume:

# trace:
# match
