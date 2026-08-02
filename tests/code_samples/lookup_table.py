key = "create"

# before:
result = {"create": 1, "delete": 2}[key]
print(result)

# after:
match key:
    case "create":
        result = 1
    case "delete":
        result = 2
    case _matchify_key:
        raise KeyError(_matchify_key)
print(result)

# assume: lookup-equality

# trace:
# 1
