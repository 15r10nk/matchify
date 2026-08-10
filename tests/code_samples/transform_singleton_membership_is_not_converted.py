# before:
value = 1
if value in (True,):
    print("true-ish")
elif value in (False,):
    print("false-ish")

# after:
value = 1
if value in (True,):
    print("true-ish")
elif value in (False,):
    print("false-ish")

# assume:

# trace:
# true-ish
