# before:
x = {"a": 1, "b": 2}
# This would be x["a"] which we don't support
if len(x) == 2:
    print("two items")
elif x == 0:
    print("zero")

# after:
x = {"a": 1, "b": 2}
# This would be x["a"] which we don't support
if len(x) == 2:
    print("two items")
elif x == 0:
    print("zero")

# assume:

# trace:
# two items
