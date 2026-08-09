# before:
def lookup(key):
    methods = {"a": 1}
    return methods[:]
try:
    print(lookup('a'))
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
def lookup(key):
    methods = {"a": 1}
    return methods[:]
try:
    print(lookup('a'))
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# KeyError
