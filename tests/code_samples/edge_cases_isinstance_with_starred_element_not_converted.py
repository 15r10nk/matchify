# before:
types = (int, str)
value = 42
if isinstance(value, (*types,)):
    print("matches")
elif value == 0:
    print("zero")

# after:
types = (int, str)
value = 42
if isinstance(value, (*types,)):
    print("matches")
elif value == 0:
    print("zero")

# assume:

# trace:
# matches
