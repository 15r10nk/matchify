# before:
data = [1, 42]
enabled = ready = True
if len(data) == 2 and data[0] == 1 and enabled and ready:
    result = data[1]
    print(result)
elif len(data) == 2 and data[0] == 2 and enabled and ready:
    result = data[1]
    print(result)

# after:
data = [1, 42]
enabled = ready = True
match data:
    case 1, result if enabled and ready:
        print(result)
    case 2, result if enabled and ready:
        print(result)

# assume:
# convert-if: sequence_checks == 2 and guard_conditions == 4 and captures == 2

# trace:
# 42
