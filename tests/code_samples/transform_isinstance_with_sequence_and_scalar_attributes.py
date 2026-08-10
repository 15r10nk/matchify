# before:
class Container:
    def __init__(self, items, count):
        self.items = items
        self.count = count

obj = Container([1, 2, 3], 3)
if isinstance(obj, Container) and len(obj.items) == 3 and obj.items[0] == 1 and obj.items[1] == 2 and obj.items[2] == 3 and obj.count == 3:
    print("match")
elif isinstance(obj, Container):
    print("other")

# after:
class Container:
    def __init__(self, items, count):
        self.items = items
        self.count = count

obj = Container([1, 2, 3], 3)
match obj:
    case Container(items=[1, 2, 3], count=3):
        print("match")
    case Container():
        print("other")

# assume:

# trace:
# match
