# before:
class Point:
    pass

class Node:
    pass

value = Point()
if isinstance(value, Point) or isinstance(value, Node):
    print("class")
elif value == 1:
    print("one")

# after:
class Point:
    pass

class Node:
    pass

value = Point()
match value:
    case Point() | Node():
        print("class")
    case 1:
        print("one")

# assume:

# trace:
# class
