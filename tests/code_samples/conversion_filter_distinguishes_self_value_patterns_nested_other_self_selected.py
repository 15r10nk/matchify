# before:
from types import SimpleNamespace

other = SimpleNamespace(val=2, self=SimpleNamespace(val=2))

def first():
    print("first")

def second():
    print("second")

for value in (2, 0, 1):
    if value == other.self.val:
        first()
    elif value == 0:
        second()
    else:
        print("other")

# after:
from types import SimpleNamespace

other = SimpleNamespace(val=2, self=SimpleNamespace(val=2))

def first():
    print("first")

def second():
    print("second")

for value in (2, 0, 1):
    match value:
        case other.self.val:
            first()
        case 0:
            second()
        case _:
            print("other")

# assume:
# convert-if: self_value_patterns == 0

# trace:
# first
# second
# other
