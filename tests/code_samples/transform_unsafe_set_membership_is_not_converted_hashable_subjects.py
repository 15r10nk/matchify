# before:
value = "a"

def make_value():
    return "a"

class Constants:
    VALUE = "a"

values = {"a"}
if value in {*values}:
    print("starred")
elif value in {"b"}:
    print("literal")

if value in {make_value()}:
    print("dynamic")
elif value in {"b"}:
    print("literal")

if value in {Constants.VALUE}:
    print("qualified")
elif value in {"b"}:
    print("literal")

if value in {"a", "a"}:
    print("duplicate")
elif value in {"b"}:
    print("literal")

# after:
value = "a"

def make_value():
    return "a"

class Constants:
    VALUE = "a"

values = {"a"}
if value in {*values}:
    print("starred")
elif value in {"b"}:
    print("literal")

if value in {make_value()}:
    print("dynamic")
elif value in {"b"}:
    print("literal")

if value in {Constants.VALUE}:
    print("qualified")
elif value in {"b"}:
    print("literal")

if value in {"a", "a"}:
    print("duplicate")
elif value in {"b"}:
    print("literal")

# assume: hashable-subjects
# ignore-types: .*_TYPES$

# trace:
# starred
# dynamic
# qualified
# duplicate
