# before:
point = (1, 2)
if len(point) == 2 and point[0] == 1 and point[1] > 0:
    print("positive second")
elif len(point) == 2 and point[0] == 0:
    print("zero")

# after:
point = (1, 2)
match point:
    case 1, _ if point[1] > 0:
        print("positive second")
    case 0, _:
        print("zero")

# assume:

# trace:
# positive second
