# before:
def lookup(key):
    return methods[key]
    methods = {"a": 1}
try:
    print(lookup('a'))
except UnboundLocalError as error:
    print(type(error).__name__)

# after:
def lookup(key):
    return methods[key]
    methods = {"a": 1}
try:
    print(lookup('a'))
except UnboundLocalError as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# UnboundLocalError
