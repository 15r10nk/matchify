# before:
key = "a"
_matchify_key = {"a": 1}[key]
print(_matchify_key)

# after:
key = "a"
match key:
    case "a":
        _matchify_key = 1
    case _matchify_key_2:
        raise KeyError(_matchify_key_2)
print(_matchify_key)

# assume: lookup-equality

# trace:
# 1
