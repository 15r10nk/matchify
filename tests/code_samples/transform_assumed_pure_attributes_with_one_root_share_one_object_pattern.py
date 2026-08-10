# before:
class Value: pass
value = Value()
value.x = 1
value.y = 2

if value.x == 1 and value.y == 2:
    print("first")
elif value.x == 3 and value.y == 4:
    print("second")

# after:
class Value: pass
value = Value()
value.x = 1
value.y = 2

match value:
    case object(x=1, y=2):
        print("first")
    case object(x=3, y=4):
        print("second")

# assume: use-object

# trace:
# first
