# before:
x = [[1, 2], 3]
if len(x) == 2 and len(x[0]) == 2 and x[0][0] == 1 and x[0][1] == 2 and x[1] == 3:
    print("match")
elif x == 0:
    print("zero")

# after:
x = [[1, 2], 3]
match x:
    case [1, 2], 3:
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
