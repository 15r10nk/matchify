# before:
from enum import Enum

class Op(Enum):
    ADD = 1
    SUBTRACT = 2

op = Op.SUBTRACT
op2 = Op.ADD

if op == Op.ADD:
    print("add")
elif op == Op.SUBTRACT and op2 == Op.ADD:
    print("subtract add")
elif op == Op.SUBTRACT and op2 == Op.SUBTRACT:
    print("subtract subtract")

# after:
from enum import Enum

class Op(Enum):
    ADD = 1
    SUBTRACT = 2

op = Op.SUBTRACT
op2 = Op.ADD

match (op, op2):
    case Op.ADD, _:
        print("add")
    case Op.SUBTRACT, Op.ADD:
        print("subtract add")
    case Op.SUBTRACT, Op.SUBTRACT:
        print("subtract subtract")

# assume: pure-subjects
# ignore-types: .*_TYPES$

# trace:
# subtract add
