# before:
ENABLED = True
value = 1
if value == 1 and ENABLED:
    print("enabled one")
elif value == 2:
    print("two")

# after:
ENABLED = True
value = 1
match value:
    case 1 if ENABLED:
        print("enabled one")
    case 2:
        print("two")

# assume:

# trace:
# enabled one
