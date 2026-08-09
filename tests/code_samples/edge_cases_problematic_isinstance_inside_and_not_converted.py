# before:
SYMBOL_TYPES = (str,)
x = "value"
if isinstance(x, int) and isinstance(x, SYMBOL_TYPES):
    print("ignored type variable")
elif isinstance(x, str):
    print("str")

# after:
SYMBOL_TYPES = (str,)
x = "value"
if isinstance(x, int) and isinstance(x, SYMBOL_TYPES):
    print("ignored type variable")
elif isinstance(x, str):
    print("str")

# assume:
# ignore-types: .*_TYPES$

# trace:
# str
