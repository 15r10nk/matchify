# before:
from types import SimpleNamespace

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
other = SimpleNamespace(val=2, self=SimpleNamespace(val=2))
value = 1

def first():
    print("first")

def second():
    print("second")

if value in (self.val, other.val, self.other):
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
other = SimpleNamespace(val=2, self=SimpleNamespace(val=2))
value = 1

def first():
    print("first")

def second():
    print("second")

match value:
    case self.val | other.val | self.other:
        first()
    case 0:
        second()

# assume:
# convert-if: self_value_patterns == 2

# trace:
# first
