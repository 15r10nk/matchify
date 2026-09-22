# before:
expected = 1
point = (1, 2)
if len(point) == 2 and point[0] == expected:
    print("expected first")
elif len(point) == 2 and point[0] == 0:
    print("zero")

# after:
expected = 1
point = (1, 2)
if len(point) == 2 and point[0] == expected:
    print("expected first")
elif len(point) == 2 and point[0] == 0:
    print("zero")

# assume:

# trace:
# expected first
