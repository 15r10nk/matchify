# before:
class Data:
    def __init__(self, vals):
        self.vals = vals

d = Data([10, 20, 30, 40, 50, 60])
if isinstance(d, Data) and len(d.vals) >= 6:
    a = d.vals[0]
    b = d.vals[1]
    d_val = d.vals[3]
    f = d.vals[5]
    print(a, b, d_val, f)
elif isinstance(d, Data):
    print("other")

# after:
class Data:
    def __init__(self, vals):
        self.vals = vals

d = Data([10, 20, 30, 40, 50, 60])
match d:
    case Data(vals=[a, b, _, d_val, _, f, *_]):
        print(a, b, d_val, f)
    case Data():
        print("other")

# assume:

# trace:
# 10 20 40 60
