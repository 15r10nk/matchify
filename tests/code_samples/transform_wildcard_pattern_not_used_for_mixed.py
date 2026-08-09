# before:
data = [1, "middle", 3]
if len(data) == 3 and data[0] == 1 and data[2] == 3:
    print(f"1 and 3 with {data[1]} in middle")
elif len(data) == 3 and data[0] == 0 and data[2] == 2:
    print(f"0 and 2 with {data[1]} in middle")

# after:
data = [1, "middle", 3]
match data:
    case 1, _, 3:
        print(f"1 and 3 with {data[1]} in middle")
    case 0, _, 2:
        print(f"0 and 2 with {data[1]} in middle")

# assume:

# trace:
# 1 and 3 with middle in middle
