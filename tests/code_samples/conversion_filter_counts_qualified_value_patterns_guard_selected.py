# before:
from types import SimpleNamespace

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
value = 1

def check(value):
    return True

def first():
    print("first")

def second():
    print("second")

if value == 1 and check(self.val):
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
value = 1

def check(value):
    return True

def first():
    print("first")

def second():
    print("second")

match value:
    case 1 if check(self.val):
        first()
    case 0:
        second()

# assume:
# convert-if: value_patterns == 0

# trace:
# first
