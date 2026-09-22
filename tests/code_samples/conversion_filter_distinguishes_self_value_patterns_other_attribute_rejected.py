# before:
from types import SimpleNamespace

other = SimpleNamespace(val=2, self=SimpleNamespace(val=2))
value = 1

def first():
    print("first")

def second():
    print("second")

if value == other.val:
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

other = SimpleNamespace(val=2, self=SimpleNamespace(val=2))
value = 1

def first():
    print("first")

def second():
    print("second")

if value == other.val:
    first()
elif value == 0:
    second()

# assume:
# convert-if: not (self_value_patterns == 0)

# trace:
