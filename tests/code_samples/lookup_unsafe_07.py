# before:
start = None
stop = None

def lookup():
    return {"a": 1}[start:stop]

try:
    print(lookup())
except (KeyError, TypeError):
    print("lookup failed")

# after:
start = None
stop = None

def lookup():
    return {"a": 1}[start:stop]

try:
    print(lookup())
except (KeyError, TypeError):
    print("lookup failed")

# assume: lookup-equality

# trace:
# lookup failed
