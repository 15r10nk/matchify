# before:
key = "a"

def lookup():
    return {"a": 1}[key] + {"b": 2}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
key = "a"

def lookup():
    return {"a": 1}[key] + {"b": 2}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# KeyError
