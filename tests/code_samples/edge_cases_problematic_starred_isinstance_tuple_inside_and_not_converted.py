# before:
types = (str,)
x = "value"
if isinstance(x, int) and isinstance(x, (*types,)):
    print("starred tuple")
elif isinstance(x, str):
    print("str")

# after:
types = (str,)
x = "value"
if isinstance(x, int) and isinstance(x, (*types,)):
    print("starred tuple")
elif isinstance(x, str):
    print("str")

# assume:

# trace:
# str
