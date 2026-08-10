# before:
class Color:
    pass
value = None
if value is None:
    print("none")
elif isinstance(value, Color):
    print("color")
elif isinstance(value, str):
    print("string")

# after:
class Color:
    pass
value = None
match value:
    case None:
        print("none")
    case Color():
        print("color")
    case str():
        print("string")

# assume:

# trace:
# none
