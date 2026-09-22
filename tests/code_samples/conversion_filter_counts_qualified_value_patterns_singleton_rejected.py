# before:
value = 1

def first():
    print("first")

def second():
    print("second")

value = None
if value is None:
    first()
elif value == 0:
    second()

# after:
value = 1

def first():
    print("first")

def second():
    print("second")

value = None
if value is None:
    first()
elif value == 0:
    second()

# assume:
# convert-if: not (value_patterns == 0)

# trace:
# first
