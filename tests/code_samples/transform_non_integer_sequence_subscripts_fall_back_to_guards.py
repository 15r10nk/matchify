# before:
class Data(list):
    def __getitem__(self, index):
        if isinstance(index, tuple): return 0
        return super().__getitem__(index)
data = Data([1, 2])
i = 0
if len(data) == 2 and data[0, 1] == 1:
    print("tuple subscript")
elif len(data) == 2 and data[0:1] == 1:
    print("slice subscript")
elif len(data) == 2 and data[i] == 1:
    print("dynamic subscript")
elif len(data) == 2 and data[0] == 1:
    print("one")

# after:
class Data(list):
    def __getitem__(self, index):
        if isinstance(index, tuple): return 0
        return super().__getitem__(index)
data = Data([1, 2])
i = 0
match data:
    case _, _ if data[0, 1] == 1:
        print("tuple subscript")
    case _, _ if data[0:1] == 1:
        print("slice subscript")
    case _, _ if data[i] == 1:
        print("dynamic subscript")
    case 1, _:
        print("one")

# assume:

# trace:
# dynamic subscript
