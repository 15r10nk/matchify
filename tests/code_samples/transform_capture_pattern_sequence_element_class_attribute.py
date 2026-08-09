# before:
class Point:
    def __init__(self, items):
        self.items = items

value = [Point([1, 2, 3])]
if len(value) == 1 and isinstance(value[0], Point) and len(value[0].items) >= 1:
    item = value[0].items[0]
    print(item)
elif value == 0:
    print("zero")

# after:
class Point:
    def __init__(self, items):
        self.items = items

value = [Point([1, 2, 3])]
match value:
    case Point(items=[item, *_]),:
        print(item)
    case 0:
        print("zero")

# assume:

# trace:
# 1
