# before:
from types import SimpleNamespace

selfish = SimpleNamespace(val=2)
value = 1

def first():
    print("first")

def second():
    print("second")

if value == selfish.val:
    first()
elif value == 0:
    second()

# after:
from types import SimpleNamespace

selfish = SimpleNamespace(val=2)
value = 1

def first():
    print("first")

def second():
    print("second")

match value:
    case selfish.val:
        first()
    case 0:
        second()

# assume:
# convert-if: self_value_patterns == 0

# trace:
