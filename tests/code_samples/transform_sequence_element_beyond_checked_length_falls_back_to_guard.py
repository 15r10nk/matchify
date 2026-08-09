# before:
class Data(list):
    def __getitem__(self, index):
        if index == 2: return 0
        return super().__getitem__(index)
data = Data([1])
if len(data) == 1 and data[2] == 3:
    print("too far")
elif len(data) == 1 and data[0] == 1:
    print("one")

# after:
class Data(list):
    def __getitem__(self, index):
        if index == 2: return 0
        return super().__getitem__(index)
data = Data([1])
match data:
    case _ if len(data) == 1 and data[2] == 3:
        print("too far")
    case 1,:
        print("one")

# assume:

# trace:
# one
