# before:
value = 2
enabled = True

if ((value == 1 or value == 2) and enabled) or (value == 3 and enabled):
    result = "enabled"
elif value == 4:
    result = "four"
print(result)

# after:
value = 2
enabled = True

match value:
    case 1 | 2 | 3 if enabled:
        result = "enabled"
    case 4:
        result = "four"
print(result)

# assume:

# trace:
# enabled
