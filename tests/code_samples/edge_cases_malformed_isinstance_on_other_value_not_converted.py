# before:
x = "value"
y = object()
if isinstance(x, int) and isinstance(y):
    print("bad guard")
elif isinstance(x, str):
    print("str")

# after:
x = "value"
y = object()
if isinstance(x, int) and isinstance(y):
    print("bad guard")
elif isinstance(x, str):
    print("str")

# assume:

# trace:
# str
