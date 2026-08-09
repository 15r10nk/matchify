# before:
ENABLED = True
point = (1, 2)
if len(point) == 2 and point[0] == 1 and ENABLED:
    print("enabled one")
elif len(point) == 2 and point[0] == 0:
    print("zero")

# after:
ENABLED = True
point = (1, 2)
match point:
    case 1, _ if ENABLED:
        print("enabled one")
    case 0, _:
        print("zero")

# assume:

# trace:
# enabled one
