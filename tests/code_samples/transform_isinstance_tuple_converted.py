# before:
value = 42
if isinstance(value, (int, float)):
    print("number")
elif isinstance(value, str):
    print("string")
else:
    print("other")

# after:
value = 42
match value:
    case int() | float():
        print("number")
    case str():
        print("string")
    case _:
        print("other")

# assume:

# trace:
# number
