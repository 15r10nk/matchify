# before:
a = "create"
b = "POST"
try:
    print({"create": {"POST": "a"}, "read": {"GET": "b"}}[a], {}[a][b])
except KeyError as error:
    print(type(error).__name__, error.args)

# after:
a = "create"
b = "POST"
try:
    match a:
        case "create":
            print({"POST": "a"}, {}[a][b])
        case "read":
            print({"GET": "b"}, {}[a][b])
        case _matchify_key:
            raise KeyError(_matchify_key)
except KeyError as error:
    print(type(error).__name__, error.args)

# assume: lookup-equality

# trace:
# KeyError ('create',)
