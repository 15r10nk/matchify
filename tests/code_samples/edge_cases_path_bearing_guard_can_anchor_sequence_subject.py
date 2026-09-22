# before:
class Value:
    value = 1


data = [Value()]
if len(data) == 1 and hasattr(data[0], "value"):
    print("attribute")
elif len(data) == 1 and data[0] == 0:
    print("zero")

# after:
class Value:
    value = 1


data = [Value()]
match data:
    case _, if hasattr(data[0], "value"):
        print("attribute")
    case 0,:
        print("zero")

# assume:

# trace:
# attribute
