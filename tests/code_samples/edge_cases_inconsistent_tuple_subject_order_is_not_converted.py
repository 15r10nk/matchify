# before:
class Value: pass
a = Value()
a.x = 1
b = Value()
b.y = 2

if (a.x, b.y) == (1, 2):
    print("first")
elif (b.y, a.x) == (3, 4):
    print("second")

# after:
class Value: pass
a = Value()
a.x = 1
b = Value()
b.y = 2

if (a.x, b.y) == (1, 2):
    print("first")
elif (b.y, a.x) == (3, 4):
    print("second")

# assume:

# trace:
# first
