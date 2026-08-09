# before:
x = None
if x is not None:
    print("value")
elif x is None:
    print("none")

# after:
x = None
if x is not None:
    print("value")
elif x is None:
    print("none")

# assume:

# trace:
# none
