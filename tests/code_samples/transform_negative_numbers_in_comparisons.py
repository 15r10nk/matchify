# before:
x = -5
if x == -5:
    print("negative five")
elif x == -10:
    print("negative ten")
else:
    print("other")

# after:
x = -5
match x:
    case -5:
        print("negative five")
    case -10:
        print("negative ten")
    case _:
        print("other")

# assume:

# trace:
# negative five
