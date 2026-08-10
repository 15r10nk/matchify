# before:
class Token:
    pass

value = [1, 2]
if (len(value) == 2 and value[0] == 1 and value[1] == 2) or isinstance(value, Token):
    print("match")
elif value is None:
    print("none")

# after:
class Token:
    pass

value = [1, 2]
match value:
    case [1, 2] | Token():
        print("match")
    case None:
        print("none")

# assume:

# trace:
# match
