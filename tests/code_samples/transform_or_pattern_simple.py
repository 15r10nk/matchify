# before:
x = 1
if x == 1 or x == 2:
    print("one or two")
elif x == 3 or x == 4:
    print("three or four")
else:
    print("other")

# after:
x = 1
match x:
    case 1 | 2:
        print("one or two")
    case 3 | 4:
        print("three or four")
    case _:
        print("other")

# assume:

# trace:
# one or two
