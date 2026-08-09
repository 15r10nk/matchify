# before:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = [Point(x=Token(x=[1, 2])), -1]
if len(value) == 2 and isinstance(value[0], (Point, Token)) and isinstance(value[0].x, Token) and len(value[0].x.x) >= 2 and value[1] == -1:
    item = value[0].x.x[1]
    print(item)
elif value is False:
    print("false")

# after:
class Point:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

class Token:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

value = [Point(x=Token(x=[1, 2])), -1]
match value:
    case Point(x=Token(x=[_, item, *_])) | Token(x=Token(x=[_, item, *_])), -1:
        print(item)
    case False:
        print("false")

# assume:

# trace:
# 2
