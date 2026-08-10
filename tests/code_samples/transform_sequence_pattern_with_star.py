# before:
data = [1, 2, 3, 4, 5]
if len(data) >= 2 and data[0] == 1 and data[1] == 2:
    print("starts with 1, 2")
elif len(data) >= 1 and data[0] == 0:
    print("starts with 0")
else:
    print("other")

# after:
data = [1, 2, 3, 4, 5]
match data:
    case 1, 2, *_:
        print("starts with 1, 2")
    case 0, *_:
        print("starts with 0")
    case _:
        print("other")

# assume:

# trace:
# starts with 1, 2
