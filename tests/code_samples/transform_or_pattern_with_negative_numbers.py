# before:
temp = -5
if temp == -5 or temp == -10:
    print("very cold")
elif temp == 0 or temp == 5:
    print("cold")

# after:
temp = -5
match temp:
    case -5 | -10:
        print("very cold")
    case 0 | 5:
        print("cold")

# assume:

# trace:
# very cold
