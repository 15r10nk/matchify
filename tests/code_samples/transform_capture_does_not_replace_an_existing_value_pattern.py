# before:
value = [2]
if len(value) == 1 and value[0] == 1:
    item = value[0]
    print(item)
elif value == 0:
    print("zero")
else:
    print("other")

# after:
value = [2]
match value:
    case 1,:
        item = value[0]
        print(item)
    case 0:
        print("zero")
    case _:
        print("other")

# assume:

# trace:
# other
