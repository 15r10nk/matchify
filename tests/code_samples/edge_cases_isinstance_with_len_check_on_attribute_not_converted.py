# before:
class RefExpr:
    def __init__(self, fullname, args=None):
        self.fullname = fullname
        self.args = args if args else []

class CallExpr:
    def __init__(self, callee):
        self.callee = callee

for o in (
    CallExpr(RefExpr("builtins.isinstance", [1, 2])),
    CallExpr(RefExpr("builtins.isinstance", [1])),
    CallExpr(RefExpr("custom.call", [1, 2])),
):
    if isinstance(o.callee, RefExpr) and o.callee.fullname == "builtins.isinstance" and len(o.callee.args) == 2:
        print("isinstance with 2 args")
    elif isinstance(o.callee, RefExpr):
        print("other RefExpr")

# after:
class RefExpr:
    def __init__(self, fullname, args=None):
        self.fullname = fullname
        self.args = args if args else []

class CallExpr:
    def __init__(self, callee):
        self.callee = callee

for o in (
    CallExpr(RefExpr("builtins.isinstance", [1, 2])),
    CallExpr(RefExpr("builtins.isinstance", [1])),
    CallExpr(RefExpr("custom.call", [1, 2])),
):
    if isinstance(o.callee, RefExpr) and o.callee.fullname == "builtins.isinstance" and len(o.callee.args) == 2:
        print("isinstance with 2 args")
    elif isinstance(o.callee, RefExpr):
        print("other RefExpr")

# assume:

# trace:
# isinstance with 2 args
# other RefExpr
# other RefExpr
