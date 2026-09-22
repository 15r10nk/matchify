# before:
class Data:
    def __init__(self, values):
        self.values = values

d = Data([10, 20, 30])
if isinstance(d, Data) and len(d.values) >= 3:
    a = d.values[0]
    b = d.values[1]
    c = d.values[2]
    print(a, b, c)
elif isinstance(d, Data):
    print("other")

# after:
class Data:
    def __init__(self, values):
        self.values = values

d = Data([10, 20, 30])
match d:
    case Data(values=[a, b, c, *_]):
        print(a, b, c)
    case Data():
        print("other")

# assume:

# trace:
# 10 20 30
