# before:
def choose(value, callback=lambda x: (x + 1)) -> tuple[int, str]:
    try:
        match value:
            case int():
                if value == 1:
                    result = (callback( value ), "first")  # keep spacing
                elif value == 2:
                    result = (callback( value ), "second")
                else:
                    result = (callback( value ), "other")
    finally:
        callback(0)
    return result
result = [choose(value) for value in (1, 2, 3)]
print(result)

# after:
def choose(value, callback=lambda x: (x + 1)) -> tuple[int, str]:
    try:
        match value:
            case int():
                match value:
                    case 1:
                        result = (callback( value ), "first")  # keep spacing
                    case 2:
                        result = (callback( value ), "second")
                    case _:
                        result = (callback( value ), "other")
    finally:
        callback(0)
    return result
result = [choose(value) for value in (1, 2, 3)]
print(result)

# assume:

# trace:
# [(2, 'first'), (3, 'second'), (4, 'other')]
