# before:
def method(operation):
    methods = {"create": "POST", "read": "GET"}
    return methods[operation]
print(method("create"))

# after:
def method(operation):
    match operation:
        case "create":
            return "POST"
        case "read":
            return "GET"
        case _matchify_key:
            raise KeyError(_matchify_key)
print(method("create"))

# assume: lookup-equality

# trace:
# POST
