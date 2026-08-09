# before:
class A:
    pass

class B:
    pass

class C:
    pass

x = A()
y = B()
if isinstance(x, A) and isinstance(y, B):
    print("both")
elif isinstance(x, C):
    print("c")

# after:
class A:
    pass

class B:
    pass

class C:
    pass

x = A()
y = B()
match x:
    case A() if isinstance(y, B):
        print("both")
    case C():
        print("c")

# assume:

# trace:
# both
