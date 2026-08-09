# before:
num = 1
if num == 0:
    print("zero")
elif num == 1:
    print("one")
elif num == 2:
    print("two")

# after:
num = 1
match num:
    case 0:
        print("zero")
    case 1:
        print("one")
    case 2:
        print("two")

# assume:

# trace:
# one
