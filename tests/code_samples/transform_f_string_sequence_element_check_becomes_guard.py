# before:
value = [f"ready"]
if len(value) == 1 and value[0] == f"ready":
    print("ready")
elif value == 0:
    print("zero")

# after:
value = [f"ready"]
if len(value) == 1 and value[0] == f"ready":
    print("ready")
elif value == 0:
    print("zero")

# assume:

# trace:
# ready
