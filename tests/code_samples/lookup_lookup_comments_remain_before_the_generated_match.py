# before:
operation = "create"
# lookup comment
print({"create": "POST", "read": "GET"}[operation])

# after:
operation = "create"
# lookup comment
match operation:
    case "create":
        print("POST")
    case "read":
        print("GET")
    case _matchify_key:
        raise KeyError(_matchify_key)

# assume: lookup-equality

# trace:
# POST
