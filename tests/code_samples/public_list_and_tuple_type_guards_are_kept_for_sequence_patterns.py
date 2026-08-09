# before:
value = [1]

if isinstance(value, list) and len(value) == 1:
    result = "list"
elif isinstance(value, tuple) and len(value) == 2:
    result = "tuple"
print(result)

# after:
value = [1]

match value:
    case _, if isinstance(value, list):
        result = "list"
    case _, _ if isinstance(value, tuple):
        result = "tuple"
print(result)

# assume:

# trace:
# list
