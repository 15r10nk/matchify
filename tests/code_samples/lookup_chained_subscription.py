# before:
def lookup(a, b):
    methods = {"a": {"b": 1}}
    return methods[a][b]
print(lookup("a", "b"))

# after:
def lookup(a, b):
    methods = {"a": {"b": 1}}
    return methods[a][b]
print(lookup("a", "b"))

# assume: lookup-equality

# trace:
# 1
