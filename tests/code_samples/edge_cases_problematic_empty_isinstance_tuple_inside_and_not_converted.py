# before:
x = "value"
if isinstance(x, int) and isinstance(x, ()):
    print("empty tuple")
elif isinstance(x, str):
    print("str")

# after:
x = "value"
if isinstance(x, int) and isinstance(x, ()):
    print("empty tuple")
elif isinstance(x, str):
    print("str")

# assume:

# trace:
# str
