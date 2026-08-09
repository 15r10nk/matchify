# before:
value = [1, 2]
if len(value) == 2 and value[1] == 2:
    first = value[0]
    print(first)
elif value is None:
    print("none")

# after:
value = [1, 2]
match value:
    case first, 2:
        print(first)
    case None:
        print("none")

# assume:

# trace:
# 1
