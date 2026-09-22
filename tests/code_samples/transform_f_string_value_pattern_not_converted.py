# before:
value = f"ready"
if value == f"ready":
    print("ready")
elif value == "other":
    print("other")

# after:
value = f"ready"
if value == f"ready":
    print("ready")
elif value == "other":
    print("other")

# assume:

# trace:
# ready
