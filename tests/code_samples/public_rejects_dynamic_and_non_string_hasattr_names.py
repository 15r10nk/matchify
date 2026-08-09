# before:
value = type('Value', (), {'field': 1})()
name = "field"
if hasattr(value, name):
    result = "dynamic"
elif hasattr(value, b"field"):
    result = "bytes"
print(result)

# after:
value = type('Value', (), {'field': 1})()
name = "field"
if hasattr(value, name):
    result = "dynamic"
elif hasattr(value, b"field"):
    result = "bytes"
print(result)

# assume:

# trace:
# dynamic
