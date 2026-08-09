# before:
point = (1, 2, 3)
if len(point) == 3 and point[0] == 1 and point[1] == 2:
    print("incomplete")
elif len(point) == 3:
    print("complete")

# after:
point = (1, 2, 3)
if len(point) == 3 and point[0] == 1 and point[1] == 2:
    print("incomplete")
elif len(point) == 3:
    print("complete")

# assume:

# trace:
# incomplete
