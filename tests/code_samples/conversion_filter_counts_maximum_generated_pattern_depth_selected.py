# before:
class Position:
    x = 1

class Point:
    position = Position()

node = Point()

if isinstance(node, Point) and isinstance(node.position, Position) and node.position.x == 1:
    print("one")
elif isinstance(node, Point) and isinstance(node.position, Position) and node.position.x == 2:
    print("two")

# after:
class Position:
    x = 1

class Point:
    position = Position()

node = Point()

match node:
    case Point(position=Position(x=1)):
        print("one")
    case Point(position=Position(x=2)):
        print("two")

# assume:
# convert-if: max_pattern_depth == 3

# trace:
# one
