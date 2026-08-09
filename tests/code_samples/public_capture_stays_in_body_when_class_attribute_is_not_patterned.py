# before:
class First:
    items = ["captured"]
class Second: pass
value = First()

if isinstance(value, First):
    item = value.items[0]
    result = item
elif isinstance(value, Second):
    result = "second"
print(result)

# after:
class First:
    items = ["captured"]
class Second: pass
value = First()

match value:
    case First():
        item = value.items[0]
        result = item
    case Second():
        result = "second"
print(result)

# assume:

# trace:
# captured
