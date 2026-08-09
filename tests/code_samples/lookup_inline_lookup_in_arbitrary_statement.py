operation = "create"


def consume(value):
    print(value)


# before:
consume({"create": "POST", "read": "GET"}[operation])

# after:
match operation:
    case "create":
        consume("POST")
    case "read":
        consume("GET")
    case _matchify_key:
        raise KeyError(_matchify_key)

# assume: lookup-equality

# trace:
# POST
