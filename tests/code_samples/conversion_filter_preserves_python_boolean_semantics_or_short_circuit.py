# before:
value = 1
if value == 1:
    pass
elif value == 2:
    pass

# after:
value = 1
match value:
    case 1:
        pass
    case 2:
        pass

# assume:
# convert-if: branches or 1 / 0

# trace:
