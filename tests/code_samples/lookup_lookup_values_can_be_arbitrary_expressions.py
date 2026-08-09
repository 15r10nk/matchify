class Settings:
    value = "attribute"


def make_value():
    return "call"


settings = Settings()
key = "expression"
left = 1
right = 2

# before:
result = {
    "call": make_value(),
    "attribute": settings.value,
    "containers": [1, {"nested": key}],
    "expression": left + right,
}[key]
print(result)

# after:
match key:
    case "call":
        result = make_value()
    case "attribute":
        result = settings.value
    case "containers":
        result = [1, {"nested": key}]
    case "expression":
        result = left + right
    case _matchify_key:
        raise KeyError(_matchify_key)
print(result)

# assume: lookup-equality

# trace:
# 3
