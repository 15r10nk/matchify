# before:
start = None
stop = None

def lookup():
    return {"a": 1}[start:stop]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
start = None
stop = None

def lookup():
    return {"a": 1}[start:stop]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# KeyError
