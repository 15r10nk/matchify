# before:
class A:
    pass
class B:
    pass
x = [1, A(), 3, B(), 5, 6, 7, 8]
if len(x) == 8 and x[0] == 1 and isinstance(x[1], A) and x[2] == 3 and isinstance(x[3], B) and x[4] == 5 and x[5] == 6 and x[6] == 7 and x[7] == 8:
    print("eight elements")
elif x == 0:
    print("zero")

# after:
class A:
    pass
class B:
    pass
x = [1, A(), 3, B(), 5, 6, 7, 8]
match x:
    case 1, A(), 3, B(), 5, 6, 7, 8:
        print("eight elements")
    case 0:
        print("zero")

# assume:

# trace:
# eight elements
