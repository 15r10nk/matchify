# before:
key = "a"
nested_key = "nested"

def lookup():
    return {"a": {"nested": 1}}[key][nested_key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
key = "a"
nested_key = "nested"

def lookup():
    return {"a": {"nested": 1}}[key][nested_key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# 1
