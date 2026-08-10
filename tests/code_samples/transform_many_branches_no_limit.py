# before:
x = 5
if x == 1:
    print("one")
elif x == 2:
    print("two")
elif x == 3:
    print("three")
elif x == 4:
    print("four")
elif x == 5:
    print("five")
elif x == 6:
    print("six")
elif x == 7:
    print("seven")
elif x == 8:
    print("eight")
elif x == 9:
    print("nine")
elif x == 10:
    print("ten")
elif x == 11:
    print("eleven")
elif x == 12:
    print("twelve")

# after:
x = 5
match x:
    case 1:
        print("one")
    case 2:
        print("two")
    case 3:
        print("three")
    case 4:
        print("four")
    case 5:
        print("five")
    case 6:
        print("six")
    case 7:
        print("seven")
    case 8:
        print("eight")
    case 9:
        print("nine")
    case 10:
        print("ten")
    case 11:
        print("eleven")
    case 12:
        print("twelve")

# assume:

# trace:
# five
