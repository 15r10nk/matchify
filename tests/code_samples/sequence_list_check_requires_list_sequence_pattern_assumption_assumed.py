# before:
value = [1]

if isinstance(value, list) and len(value) == 1 and value[0] == 1:
    result = "one"
elif value is None:
    result = "none"
print(result)

# after:
value = [1]

match value:
    case 1,:
        result = "one"
    case None:
        result = "none"
print(result)

# assume: list-sequence-pattern

# trace:
# one
