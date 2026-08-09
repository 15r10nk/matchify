# before:
class Token: A = "a"
key = "a"

def lookup():
    return {Token.A: 1}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# after:
class Token: A = "a"
key = "a"

def lookup():
    return {Token.A: 1}[key]

try:
    print(lookup())
except (KeyError, TypeError) as error:
    print(type(error).__name__)

# assume: lookup-equality

# trace:
# 1
