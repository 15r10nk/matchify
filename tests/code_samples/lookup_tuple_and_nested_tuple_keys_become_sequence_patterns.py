# before:
key = (("nested", 2), (True, None))
result = {
    ("create", 1): "simple",
    (("nested", 2), (True, None)): "nested",
    (): "empty",
    ("single",): "single",
}[key]
print(result)

# after:
key = (("nested", 2), (True, None))
match key:
    case ("create", 1):
        result = "simple"
    case (("nested", 2), (True, None)):
        result = "nested"
    case ():
        result = "empty"
    case ("single",):
        result = "single"
    case _matchify_key:
        raise KeyError(_matchify_key)
print(result)

# assume: lookup-equality

# trace:
# nested
