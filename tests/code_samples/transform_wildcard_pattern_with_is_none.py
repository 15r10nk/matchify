# before:
data = [None, "a", 3]
if len(data) == 3 and data[0] is None and data[2] == 3:
    print("none and 3 with gap")
elif len(data) == 3 and data[0] is None and data[2] == 5:
    print("none and 5 with gap")

# after:
data = [None, "a", 3]
match data:
    case None, _, 3:
        print("none and 3 with gap")
    case None, _, 5:
        print("none and 5 with gap")

# assume:

# trace:
# none and 3 with gap
