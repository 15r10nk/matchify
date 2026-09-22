# before:
calls = 0
def subject():
    global calls
    calls += 1
    return "missing"

try:
    result = {"a": 1}[subject()]
    print(result)
except KeyError as error:
    missing = error.args[0]
print(calls, missing)

# after:
calls = 0
def subject():
    global calls
    calls += 1
    return "missing"

try:
    match subject():
        case "a":
            result = 1
        case _matchify_key:
            raise KeyError(_matchify_key)
    print(result)
except KeyError as error:
    missing = error.args[0]
print(calls, missing)

# assume: lookup-equality

# trace:
# 1 missing
