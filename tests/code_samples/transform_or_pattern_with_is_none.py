# before:
value = None
if value is None or value is False:
    print("falsy singleton")
elif value is True:
    print("truthy singleton")

# after:
value = None
match value:
    case None | False:
        print("falsy singleton")
    case True:
        print("truthy singleton")

# assume:

# trace:
# falsy singleton
