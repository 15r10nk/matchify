# before:
class Value:
    i = 5
    j = 6

value = Value()
if value.i == 5:
    print("i")
elif value.j == 6:
    print("j")

# after:
class Value:
    i = 5
    j = 6

value = Value()
match value:
    case object(i=5):
        print("i")
    case object(j=6):
        print("j")

# assume: use-object
# ignore-types: .*_TYPES$

# trace:
# i
