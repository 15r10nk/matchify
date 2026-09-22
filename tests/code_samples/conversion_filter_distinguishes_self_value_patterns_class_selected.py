# before:
from types import SimpleNamespace

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
value = 1

def first():
    print("first")

def second():
    print("second")

value = Thing()
if isinstance(value, self.Kind):
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
value = 1

def first():
    print("first")

def second():
    print("second")

value = Thing()
match value:
    case self.Kind():
        first()
    case 0:
        second()

# assume:
# convert-if: self_value_patterns == 0

# trace:
# first
