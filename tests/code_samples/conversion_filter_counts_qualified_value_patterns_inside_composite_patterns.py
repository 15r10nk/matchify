# before:
from types import SimpleNamespace

class Kind:
    OTHER = 2

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
left = 1
right = 2
def first():
    print("first")

def second():
    print("second")

if left == self.val and right == Kind.OTHER:
    first()
elif left == 1 and right == 2:
    second()

# after:
from types import SimpleNamespace

class Kind:
    OTHER = 2

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
left = 1
right = 2
def first():
    print("first")

def second():
    print("second")

match (left, right):
    case self.val, Kind.OTHER:
        first()
    case 1, 2:
        second()

# assume: pure-subjects
# convert-if: value_patterns == 2 and self_value_patterns == 1

# trace:
# first
