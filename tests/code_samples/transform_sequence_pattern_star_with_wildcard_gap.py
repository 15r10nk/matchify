# before:
data = [1, 99, 3, 4, 5]
if len(data) >= 3 and data[0] == 1 and data[2] == 3:
    print("starts with 1 and third is 3")
elif len(data) >= 2 and data[1] == 0:
    print("second is 0")

# after:
data = [1, 99, 3, 4, 5]
match data:
    case 1, _, 3, *_:
        print("starts with 1 and third is 3")
    case _, 0, *_:
        print("second is 0")

# assume:

# trace:
# starts with 1 and third is 3
