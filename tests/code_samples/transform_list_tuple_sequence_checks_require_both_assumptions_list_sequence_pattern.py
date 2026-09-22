# before:
value = [1, 2]
if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1:
    print("one")
elif isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 2:
    print("two")

# after:
value = [1, 2]
if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1:
    print("one")
elif isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 2:
    print("two")

# assume: list-sequence-pattern
# ignore-types: .*_TYPES$

# trace:
# one
