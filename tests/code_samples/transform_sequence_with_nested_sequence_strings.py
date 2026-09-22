# before:
x = [["a", "b"], "c"]
if len(x) == 2 and len(x[0]) == 2 and x[0][0] == "a" and x[0][1] == "b" and x[1] == "c":
    print("match")
elif x == 0:
    print("zero")

# after:
x = [["a", "b"], "c"]
match x:
    case ["a", "b"], "c":
        print("match")
    case 0:
        print("zero")

# assume:

# trace:
# match
