# before:
value = [2, 3]
if len(value) == 2 and (value[0] == 1 or value[0] == 2) and value[1] == 3:
    print("match")
elif value == 0:
    print("zero")

# after:
value = [2, 3]
match value:
    case 1 | 2, 3:
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
