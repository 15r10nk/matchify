# before:
status = "active"
if status == "active":
    print("activate")
elif status == "inactive":
    print("deactivate")

# after:
status = "active"
match status:
    case "active":
        print("activate")
    case "inactive":
        print("deactivate")

# assume:

# trace:
# activate
