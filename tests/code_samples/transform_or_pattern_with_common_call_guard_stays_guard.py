# before:
def is_ready(): return True

class Point:
    pass

class Token:
    pass

value = Point()
if (isinstance(value, Point) and is_ready()) or (isinstance(value, Token) and is_ready()):
    print("match")
elif value is None:
    print("none")

# after:
def is_ready(): return True

class Point:
    pass

class Token:
    pass

value = Point()
match value:
    case _ if (isinstance(value, Point) and is_ready()) or (isinstance(value, Token) and is_ready()):
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
