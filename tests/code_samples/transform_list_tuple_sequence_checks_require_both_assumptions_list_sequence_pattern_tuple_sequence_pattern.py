# before:
value = [1, 2]
if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1:
    print("one")
elif isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 2:
    print("two")

# after:
value = [1, 2]
match value:
    case 1, _:
        print("one")
    case 2, _:
        print("two")

# assume: list-sequence-pattern,tuple-sequence-pattern
# ignore-types: .*_TYPES$

# trace:
# one
