# before:
class Point:
    def __init__(self, x):
        self.x = x
value = Point(+1)
if isinstance(value, Point) and value.x == +1:
    print("plus attr")
elif value == +3.5:
    print("plus float")
else:
    print("other")

# after:
class Point:
    def __init__(self, x):
        self.x = x
value = Point(+1)
match value:
    case Point(x=1):
        print("plus attr")
    case 3.5:
        print("plus float")
    case _:
        print("other")

# assume:

# trace:
# plus attr
