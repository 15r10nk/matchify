# before:
data = [1, 2, "trailing"]
if len(data) == 3 and data[0] == 1 and data[1] == 2:
    print("1, 2 then gap")
elif len(data) == 3 and data[0] == 0 and data[1] == 1:
    print("0, 1 then gap")

# after:
data = [1, 2, "trailing"]
match data:
    case 1, 2, _:
        print("1, 2 then gap")
    case 0, 1, _:
        print("0, 1 then gap")

# assume:

# trace:
# 1, 2 then gap
