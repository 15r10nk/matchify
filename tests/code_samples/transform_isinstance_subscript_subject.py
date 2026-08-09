# before:
class A:
    pass
class B:
    pass

items = [A()]
if isinstance(items[0], A):
    print("a")
elif isinstance(items[0], B):
    print("b")

# after:
class A:
    pass
class B:
    pass

items = [A()]
match items[0]:
    case A():
        print("a")
    case B():
        print("b")

# assume:

# trace:
# a
