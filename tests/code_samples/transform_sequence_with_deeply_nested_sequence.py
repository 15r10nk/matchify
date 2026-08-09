# before:
x = [[[1, 2]]]
if len(x) == 1 and len(x[0]) == 1 and len(x[0][0]) == 2 and x[0][0][0] == 1 and x[0][0][1] == 2:
    print("match")
elif x == 0:
    print("zero")

# after:
x = [[[1, 2]]]
match x:
    case [[1, 2]],:
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
