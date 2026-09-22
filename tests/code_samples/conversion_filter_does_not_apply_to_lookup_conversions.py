# before:
operation = "create"
result = {"create": "POST", "read": "GET"}[operation]
print(result)

# after:
operation = "create"
match operation:
    case "create":
        result = "POST"
    case "read":
        result = "GET"
    case _matchify_key:
        raise KeyError(_matchify_key)
print(result)

# assume: lookup-equality
# convert-if: branches > 100

# trace:
# POST
