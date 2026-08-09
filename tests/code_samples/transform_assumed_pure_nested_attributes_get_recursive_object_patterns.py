# before:
class Value: pass
value = Value()
value.left = Value()
value.left.i = 5
value.right = Value()
value.right.j = 0

if value.left.i == 5:
    print("left")
elif value.right.j == 6:
    print("right")

# after:
class Value: pass
value = Value()
value.left = Value()
value.left.i = 5
value.right = Value()
value.right.j = 0

match value:
    case object(left=object(i=5)):
        print("left")
    case object(right=object(j=6)):
        print("right")

# assume: use-object

# trace:
# left
