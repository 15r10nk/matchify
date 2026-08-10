# before:
class Wrapper:
    def __init__(self, data):
        self.data = data

value = Wrapper([1, 2, 3])
if isinstance(value, Wrapper) and ((len(value.data) >= 3 and value.data[1] == 2) or (len(value.data) >= 3 and value.data[1] == 3)):
    first = value.data[0]
    third = value.data[2]
    print(first, third)
elif value is None:
    print("none")

# after:
class Wrapper:
    def __init__(self, data):
        self.data = data

value = Wrapper([1, 2, 3])
match value:
    case Wrapper(data=[first, 2, third, *_] | [first, 3, third, *_]):
        print(first, third)
    case None:
        print("none")

# assume:

# trace:
# 1 3
