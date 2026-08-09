# before:
value = [1, 2]
if len(value) == 2 and value[1] == 2:
    first = value[0]
    duplicate = value[0]
    result = first
    print(result)
elif value is None:
    result = "none"

# after:
value = [1, 2]
match value:
    case first, 2:
        duplicate = first
        result = first
        print(result)
    case None:
        result = "none"

# assume:

# trace:
# 1
