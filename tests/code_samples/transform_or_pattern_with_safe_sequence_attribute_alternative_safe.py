# before:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(items=[1, None])
if (isinstance(value, Point) and hasattr(value, "items") and isinstance(value.items, (list, tuple)) and len(value.items) == 2 and value.items[0] == 1 and value.items[1] is None) or value == 0:
    print("match")
elif value is None:
    print("none")

# after:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = Point(items=[1, None])
if (isinstance(value, Point) and hasattr(value, "items") and isinstance(value.items, (list, tuple)) and len(value.items) == 2 and value.items[0] == 1 and value.items[1] is None) or value == 0:
    print("match")
elif value is None:
    print("none")

# assume:
# ignore-types: .*_TYPES$

# trace:
# match
