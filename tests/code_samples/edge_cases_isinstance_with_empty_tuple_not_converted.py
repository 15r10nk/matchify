# before:
x = 42
if isinstance(x, ()):
    print("empty tuple")
elif x == 42:
    print("forty two")

# after:
x = 42
if isinstance(x, ()):
    print("empty tuple")
elif x == 42:
    print("forty two")

# assume:

# trace:
# forty two
