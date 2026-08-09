# before:
data = [1, "a", "b", 4]
if len(data) == 4 and data[0] == 1 and data[3] == 4:
    print("1 and 4 with two gaps")
elif len(data) == 4 and data[0] == 0 and data[3] == 3:
    print("0 and 3 with two gaps")

# after:
data = [1, "a", "b", 4]
match data:
    case 1, _, _, 4:
        print("1 and 4 with two gaps")
    case 0, _, _, 3:
        print("0 and 3 with two gaps")

# assume:

# trace:
# 1 and 4 with two gaps
