# before:
def lookup(key):
    methods = {"a": 1}
    return methods[:]
try:
    print(lookup('a'))
except (KeyError, TypeError):
    print("lookup failed")

# after:
def lookup(key):
    methods = {"a": 1}
    return methods[:]
try:
    print(lookup('a'))
except (KeyError, TypeError):
    print("lookup failed")

# assume: lookup-equality

# trace:
# lookup failed
