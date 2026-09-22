# before:
def perform_import(val):
    if val is None:
        return None
    elif isinstance(val, str):
        return import_string(val)
    elif isinstance(val, (list, tuple)):
        return [import_string(item) for item in val]
    return val
value = []
result = perform_import(value)
print(result, result is value)

# after:
def perform_import(val):
    match val:
        case None:
            return None
        case str():
            return import_string(val)
        case list() | tuple():
            return [import_string(item) for item in val]
    return val
value = []
result = perform_import(value)
print(result, result is value)

# assume:

# trace:
# [] False
