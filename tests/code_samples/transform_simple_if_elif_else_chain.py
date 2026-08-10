# before:
x = 5
if x == 1:
    print("one")
elif x == 2:
    print("two")
else:
    print("other")

# after:
x = 5
match x:
    case 1:
        print("one")
    case 2:
        print("two")
    case _:
        print("other")

# assume:

# trace:
# other
