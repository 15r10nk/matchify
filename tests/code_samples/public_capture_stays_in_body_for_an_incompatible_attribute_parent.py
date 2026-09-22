# before:
class Value(list):
    items = ["captured"]
value = Value([1])

if len(value) == 1 and value[0] == 1:
    item = value.items[0]
    result = item
elif value is None:
    result = "none"
print(result)

# after:
class Value(list):
    items = ["captured"]
value = Value([1])

match value:
    case 1,:
        item = value.items[0]
        result = item
    case None:
        result = "none"
print(result)

# assume:

# trace:
# captured
