# before:
class Value: pass
a = Value()
a.x = 1
b = Value()
b.y = 2

if a.x == 1 and b.y == 2:
    print("first")
elif a.x == 3 and b.y == 4:
    print("second")

# after:
class Value: pass
a = Value()
a.x = 1
b = Value()
b.y = 2

match a.x:
    case 1 if b.y == 2:
        print("first")
    case 3 if b.y == 4:
        print("second")

# assume:

# trace:
# first
