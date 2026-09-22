# before:
data = ["a", 1, 2]
if len(data) == 3 and data[1] == 1 and data[2] == 2:
    print("gap then 1, 2")
elif len(data) == 3 and data[1] == 0 and data[2] == 1:
    print("gap then 0, 1")

# after:
data = ["a", 1, 2]
match data:
    case _, 1, 2:
        print("gap then 1, 2")
    case _, 0, 1:
        print("gap then 0, 1")

# assume:

# trace:
# gap then 1, 2
