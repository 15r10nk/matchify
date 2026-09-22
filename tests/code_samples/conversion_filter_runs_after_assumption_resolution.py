# before:
from types import SimpleNamespace
a = SimpleNamespace(x=1)
b = SimpleNamespace(y=2)
if a.x == 1 and b.y == 2:
    print("first")
elif a.x == 3 and b.y == 4:
    print("second")

# after:
from types import SimpleNamespace
a = SimpleNamespace(x=1)
b = SimpleNamespace(y=2)
match (a.x, b.y):
    case 1, 2:
        print("first")
    case 3, 4:
        print("second")

# assume: pure-subjects
# convert-if: patterns == 2 and guard_conditions == 0

# trace:
# first
