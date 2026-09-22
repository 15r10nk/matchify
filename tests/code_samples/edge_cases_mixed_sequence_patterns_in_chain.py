# before:
point = (1, 2)
if len(point) == 2 and point[0] == 1 and point[1] == 2:
    print("1, 2")
elif len(point) == 2 and point[0] == 0 and point[1] == 0:
    print("0, 0")
elif len(point) == 3 and point[0] == 1 and point[1] == 1 and point[2] == 1:
    print("1, 1, 1")

# after:
point = (1, 2)
match point:
    case 1, 2:
        print("1, 2")
    case 0, 0:
        print("0, 0")
    case 1, 1, 1:
        print("1, 1, 1")

# assume:

# trace:
# 1, 2
