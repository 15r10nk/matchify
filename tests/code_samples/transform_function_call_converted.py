# before:
def get_value():
    return 1
if get_value() == 1:
    print("one")
elif get_value() == 2:
    print("two")

# after:
def get_value():
    return 1
match get_value():
    case 1:
        print("one")
    case 2:
        print("two")

# assume:

# trace:
# one
