# before:
class Point:
    def __init__(self, x):
        self.x = x
class Color:
    pass
value = [Point(5), 2]
if len(value) == 2 and isinstance(value[0], Point) and value[1] == 2:
    print("sequence with point")
elif value == 42:
    print("literal")
elif isinstance(value, Color):
    print("color")
elif value is None:
    print("none")
else:
    print("other")

# after:
class Point:
    def __init__(self, x):
        self.x = x
class Color:
    pass
value = [Point(5), 2]
match value:
    case Point(), 2:
        print("sequence with point")
    case 42:
        print("literal")
    case Color():
        print("color")
    case None:
        print("none")
    case _:
        print("other")

# assume:

# trace:
# sequence with point
