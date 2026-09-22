# before:
value = [1, 2]
if (isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1 and value[1] == 2) or value is None:
    print("match")
elif value is False:
    print("false")

# after:
value = [1, 2]
match value:
    case [1, 2] | None:
        print("match")
    case False:
        print("false")

# assume: list-sequence-pattern,tuple-sequence-pattern
# ignore-types: .*_TYPES$

# trace:
# match
