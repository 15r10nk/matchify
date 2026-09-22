# before:
from types import SimpleNamespace

class Kind:
    OTHER = 2

class Thing:
    pass

package = SimpleNamespace(Kind=Kind, Thing=Thing)
value = 1

def first():
    print("first")

def second():
    print("second")

value = Thing()
if isinstance(value, package.Thing):
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

class Kind:
    OTHER = 2

class Thing:
    pass

package = SimpleNamespace(Kind=Kind, Thing=Thing)
value = 1

def first():
    print("first")

def second():
    print("second")

value = Thing()
match value:
    case package.Thing():
        first()
    case 0:
        second()

# assume:
# convert-if: value_patterns == 0

# trace:
# first
