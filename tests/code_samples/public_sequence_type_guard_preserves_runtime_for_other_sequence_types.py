# before:
value = range(1)
result = "other"
if isinstance(value, (list, tuple)) and len(value) == 1:
    result = "sequence"
elif value is None:
    result = "none"
print(result)

# after:
value = range(1)
result = "other"
match value:
    case _, if isinstance(value, (list, tuple)):
        result = "sequence"
    case None:
        result = "none"
print(result)

# assume:

# trace:
# other
