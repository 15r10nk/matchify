# before:
types = (str,)
x = 1
y = "ok"
if isinstance(x, int) and isinstance(y, (*types,)):
    print("guard")
elif isinstance(x, str):
    print("str")

# after:
types = (str,)
x = 1
y = "ok"
match x:
    case int() if isinstance(y, (*types,)):
        print("guard")
    case str():
        print("str")

# assume:

# trace:
# guard
