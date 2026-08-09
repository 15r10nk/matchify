# before:
ENABLED = True
value = 1
if (value == 1 or value is None) and ENABLED:
    print("enabled one or none")
elif value == 2:
    print("two")

# after:
ENABLED = True
value = 1
match value:
    case 1 | None if ENABLED:
        print("enabled one or none")
    case 2:
        print("two")

# assume:

# trace:
# enabled one or none
