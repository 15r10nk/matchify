# before:
data = [1, "a", "b", "c", 5]
if len(data) == 5 and data[0] == 1 and data[4] == 5:
    print("1 and 5 with three gaps")
elif len(data) == 5 and data[0] == 0 and data[4] == 4:
    print("0 and 4 with three gaps")

# after:
data = [1, "a", "b", "c", 5]
if len(data) == 5 and data[0] == 1 and data[4] == 5:
    print("1 and 5 with three gaps")
elif len(data) == 5 and data[0] == 0 and data[4] == 4:
    print("0 and 4 with three gaps")

# assume:

# trace:
# 1 and 5 with three gaps
