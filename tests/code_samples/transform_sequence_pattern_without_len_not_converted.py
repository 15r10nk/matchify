# before:
point = (1, 2)
if point[0] == 1 and point[1] == 2:
    print("no len check")
elif point[0] == 0:
    print("other")

# after:
point = (1, 2)
if point[0] == 1 and point[1] == 2:
    print("no len check")
elif point[0] == 0:
    print("other")

# assume:

# trace:
# no len check
