# before:
for value in ([[1]], [[2]], None, [], [[]]):
    result = None
    try:
        if value[0][0] == 1:
            result = "one"
        elif value is None:
            result = "none"
    except (IndexError, TypeError) as error:
        print(type(error).__name__)
    else:
        print(result)

# after:
for value in ([[1]], [[2]], None, [], [[]]):
    result = None
    try:
        match value:
            case _ if value[0][0] == 1:
                result = "one"
            case None:
                result = "none"
    except (IndexError, TypeError) as error:
        print(type(error).__name__)
    else:
        print(result)

# assume:

# trace:
# one
# None
# TypeError
# IndexError
# IndexError
