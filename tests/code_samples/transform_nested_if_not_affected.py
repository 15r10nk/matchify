# before:
x = 1
y = 2
if x == 1:
    if y == 2:
        print("nested")
    elif y == 3:
        print("three")
elif x == 3:
    print("outer three")

# after:
x = 1
y = 2
match x:
    case 1:
        match y:
            case 2:
                print("nested")
            case 3:
                print("three")
    case 3:
        print("outer three")

# assume:

# trace:
# nested
