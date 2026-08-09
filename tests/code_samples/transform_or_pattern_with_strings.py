# before:
status = "ready"
if status == "ready" or status == "running":
    print("active")
elif status == "stopped" or status == "error":
    print("inactive")

# after:
status = "ready"
match status:
    case "ready" | "running":
        print("active")
    case "stopped" | "error":
        print("inactive")

# assume:

# trace:
# active
