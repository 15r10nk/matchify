# before:
key = "a"
other = "b"

def lookup():
    return {"a": 1}[key, other]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
key = "a"
other = "b"

def lookup():
    return {"a": 1}[key, other]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# KeyError
