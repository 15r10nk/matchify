# before:
a = 1
b = 2
value = 1

def first():
    print("first")

def second():
    print("second")

def other():
    print("other")

if a == 1 and b == 2:
    if value == 1:
        first()
    elif value == 2:
        second()
elif a == 3 and b == 4:
    other()

# after:
a = 1
b = 2
value = 1

def first():
    print("first")

def second():
    print("second")

def other():
    print("other")

if a == 1 and b == 2:
    match value:
        case 1:
            first()
        case 2:
            second()
elif a == 3 and b == 4:
    other()

# assume:

# trace:
# first
