class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)


value = Point(items=[1, None])

# before:
if (
    isinstance(value, Point)
    and hasattr(value, "items")
    and isinstance(value.items, (list, tuple))
    and len(value.items) == 2
    and value.items[0] == 1
    and value.items[1] is None
):
    print("match")
elif value is None:
    print("none")

# after:
match value:
    case Point(items=[1, None]) if isinstance(value.items, (list, tuple)):
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
