# before:
value = [7, 1]

if (len(value) == 2 and value[1] == 1) or value == 0:
    item = value[0]
    result = item
elif value is None:
    result = "none"
print(result)

# after:
value = [7, 1]

match value:
    case [_, 1] | 0:
        item = value[0]
        result = item
    case None:
        result = "none"
print(result)

# assume:

# trace:
# 7
