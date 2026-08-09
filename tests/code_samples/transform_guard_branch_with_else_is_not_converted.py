# before:
value = "x"
if isinstance(value, int):
    print("int")
elif not isinstance(value, str):
    print("not string")
else:
    print("other")

# after:
value = "x"
if isinstance(value, int):
    print("int")
elif not isinstance(value, str):
    print("not string")
else:
    print("other")

# assume:

# trace:
# other
