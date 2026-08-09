# before:
x = None
if isinstance(x, (type(None), str)):
    print("optional string")
elif x == 5:
    print("five")

# after:
x = None
match x:
    case None | str():
        print("optional string")
    case 5:
        print("five")

# assume:

# trace:
# optional string
