# before:
from types import SimpleNamespace

class Kind:
    OTHER = 2

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
package = SimpleNamespace(Kind=Kind, Thing=Thing)
value = 1

def first():
    print("first")

def second():
    print("second")

if value in (self.val, package.Kind.OTHER):
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

class Kind:
    OTHER = 2

class Thing:
    pass

self = SimpleNamespace(val=1, settings=SimpleNamespace(val=1), other=2, Kind=Thing)
package = SimpleNamespace(Kind=Kind, Thing=Thing)
value = 1

def first():
    print("first")

def second():
    print("second")

if value in (self.val, package.Kind.OTHER):
    first()
elif value == 0:
    second()

# assume:
# convert-if: not (value_patterns == 2)

# trace:
# first
