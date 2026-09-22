# before:
def get_type():
    return int

x = 1
if isinstance(x, get_type()):
    print("dynamic")
elif x == 5:
    print("five")

# after:
def get_type():
    return int

x = 1
match x:
    case _ if isinstance(x, get_type()):
        print("dynamic")
    case 5:
        print("five")

# assume:

# trace:
# dynamic
