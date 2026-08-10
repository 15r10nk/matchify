# before:
x = None
if x is None:
    print("none")
elif x == 1:
    print("one")
elif x == 2:
    print("two")

# after:
x = None
match x:
    case None:
        print("none")
    case 1:
        print("one")
    case 2:
        print("two")

# assume:

# trace:
# none
