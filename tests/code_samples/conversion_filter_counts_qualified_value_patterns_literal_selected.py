# before:
value = 1

def first():
    print("first")

def second():
    print("second")

value = "text"
if value == "text":
    first()
elif value == 0:
    second()

# after:
value = 1

def first():
    print("first")

def second():
    print("second")

value = "text"
match value:
    case "text":
        first()
    case 0:
        second()

# assume:
# convert-if: value_patterns == 0

# trace:
# first
