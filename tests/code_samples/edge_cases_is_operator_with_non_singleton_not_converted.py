# before:
SENTINEL = object()
x = SENTINEL
if x is SENTINEL:
    print("sentinel")
elif x == 1:
    print("one")

# after:
SENTINEL = object()
x = SENTINEL
if x is SENTINEL:
    print("sentinel")
elif x == 1:
    print("one")

# assume:

# trace:
# sentinel
