# before:
value = 1
if value == 1 or value == 2.5:
    print("small")
elif value == 10 or value == 20.0:
    print("large")

# after:
value = 1
match value:
    case 1 | 2.5:
        print("small")
    case 10 | 20.0:
        print("large")

# assume:

# trace:
# small
