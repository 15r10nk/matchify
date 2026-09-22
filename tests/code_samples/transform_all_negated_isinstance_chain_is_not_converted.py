# before:
value = "x"
if not isinstance(value, int):
    print("not int")
elif not isinstance(value, str):
    print("not string")

# after:
value = "x"
if not isinstance(value, int):
    print("not int")
elif not isinstance(value, str):
    print("not string")

# assume:

# trace:
# not int
