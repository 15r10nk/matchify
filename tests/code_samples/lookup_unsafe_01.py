# before:
other = {}
key = "a"

def lookup():
    return {**other, "a": 1}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
other = {}
key = "a"

def lookup():
    return {**other, "a": 1}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# 1
