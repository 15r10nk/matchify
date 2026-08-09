# before:
data = [1, "middle", 3]
if len(data) == 3 and data[0] == 1 and data[2] == 3:
    print("1 and 3 with middle gap")
elif len(data) == 3 and data[0] == 0 and data[2] == 2:
    print("0 and 2 with middle gap")
else:
    print("other")

# after:
data = [1, "middle", 3]
match data:
    case 1, _, 3:
        print("1 and 3 with middle gap")
    case 0, _, 2:
        print("0 and 2 with middle gap")
    case _:
        print("other")

# assume:

# trace:
# 1 and 3 with middle gap
