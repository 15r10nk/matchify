# before:
value = [1]

if (isinstance(value, (list, tuple)) and len(value) == 1) or (isinstance(value, (list, tuple)) and len(value) == 2):
    result = "sequence"
elif value is None:
    result = "none"
print(result)

# after:
value = [1]

match value:
    case [_] | [_, _]:
        result = "sequence"
    case None:
        result = "none"
print(result)

# assume: list-sequence-pattern,tuple-sequence-pattern

# trace:
# sequence
