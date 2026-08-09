# before:
key = ("a", (1,))

def lookup():
    return {("a", [1]): "unhashable"}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
key = ("a", (1,))

def lookup():
    return {("a", [1]): "unhashable"}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# TypeError
