# before:
point = (0, 1)
if len(point) == 2 and point[0] == 0 and point[1] == 1:
    print("origin offset")
elif len(point) == 2 and point[0] == 1 and point[1] == 1:
    print("diagonal")
else:
    print("other")

# after:
point = (0, 1)
match point:
    case 0, 1:
        print("origin offset")
    case 1, 1:
        print("diagonal")
    case _:
        print("other")

# assume:

# trace:
# origin offset
