# before:
class First:
    items = 0
class Second:
    items = 2
value = Second()

if isinstance(value, First) and value.items == 1:
    item = value.items[0]
    result = item
elif isinstance(value, Second) and value.items == 2:
    result = "second"
print(result)

# after:
class First:
    items = 0
class Second:
    items = 2
value = Second()

match value:
    case First(items=1):
        item = value.items[0]
        result = item
    case Second(items=2):
        result = "second"
print(result)

# assume:

# trace:
# second
