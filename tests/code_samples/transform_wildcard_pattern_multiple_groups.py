# before:
data = [1, "a", 2, "b", "c", 5]
if len(data) == 6 and data[0] == 1 and data[2] == 2 and data[5] == 5:
    print("1, 2, 5 with gaps")
elif len(data) == 6 and data[0] == 0 and data[2] == 1 and data[5] == 3:
    print("0, 1, 3 with gaps")

# after:
data = [1, "a", 2, "b", "c", 5]
match data:
    case 1, _, 2, _, _, 5:
        print("1, 2, 5 with gaps")
    case 0, _, 1, _, _, 3:
        print("0, 1, 3 with gaps")

# assume:

# trace:
# 1, 2, 5 with gaps
