# before:
value = 1
if isinstance(value, int):
    print("int")
elif not isinstance(value, str):
    print("not string")

# after:
value = 1
if isinstance(value, int):
    print("int")
elif not isinstance(value, str):
    print("not string")

# assume:

# trace:
# int
