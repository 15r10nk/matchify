# before:
x = 1
if x == 1:
    print("one")
elif x == 2:
    print("two")
y = "a"
if y == "a":
    print("a")
elif y == "b":
    print("b")

# after:
x = 1
match x:
    case 1:
        print("one")
    case 2:
        print("two")
y = "a"
match y:
    case "a":
        print("a")
    case "b":
        print("b")

# assume:

# trace:
# one
# a
