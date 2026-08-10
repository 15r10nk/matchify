# before:
key = 1

def lookup():
    return {1: "integer", True: "boolean"}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
key = 1

def lookup():
    return {1: "integer", True: "boolean"}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# boolean
