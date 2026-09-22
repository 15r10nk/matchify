# before:
def lookup(key):
    methods = {"a": 1}
    inspect(methods)
    return methods[key]
def inspect(value): pass
print(lookup('a'))

# after:
def lookup(key):
    methods = {"a": 1}
    inspect(methods)
    return methods[key]
def inspect(value): pass
print(lookup('a'))

# assume: lookup-equality

# trace:
# 1
