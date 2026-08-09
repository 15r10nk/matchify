# before:
x = None
if isinstance(x, type(None)):
    print("none")
elif x == 5:
    print("five")

# after:
x = None
match x:
    case None:
        print("none")
    case 5:
        print("five")

# assume:

# trace:
# none
