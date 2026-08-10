# before:
value = [1, 2, 3]
if (len(value) >= 3 and value[1] == 2) or (len(value) >= 3 and value[1] == 3):
    first = value[0]
    third = value[2]
    print(first, third)
elif value is None:
    print("none")

# after:
value = [1, 2, 3]
match value:
    case [first, 2, third, *_] | [first, 3, third, *_]:
        print(first, third)
    case None:
        print("none")

# assume:

# trace:
# 1 3
