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

if value == self.settings.val:
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

if value == self.settings.val:
    first()
elif value == 0:
    second()

# assume:
# convert-if: not (self_value_patterns == 1)

# trace:
# first
