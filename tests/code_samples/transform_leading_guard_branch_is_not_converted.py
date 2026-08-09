# before:
value = 1
if not isinstance(value, str):
    print("not string")
elif isinstance(value, int):
    print("int")

# after:
value = 1
if not isinstance(value, str):
    print("not string")
elif isinstance(value, int):
    print("int")

# assume:

# trace:
# not string
