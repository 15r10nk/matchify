# before:
name = "a"
key = "a"

def lookup():
    return {name: 1}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
name = "a"
key = "a"

def lookup():
    return {name: 1}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# 1
