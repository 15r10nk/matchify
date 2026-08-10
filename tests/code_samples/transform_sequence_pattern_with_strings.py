# before:
cmd = ["get", "item"]
if len(cmd) == 2 and cmd[0] == "get" and cmd[1] == "item":
    print("get item")
elif len(cmd) == 2 and cmd[0] == "drop" and cmd[1] == "item":
    print("drop item")

# after:
cmd = ["get", "item"]
match cmd:
    case "get", "item":
        print("get item")
    case "drop", "item":
        print("drop item")

# assume:

# trace:
# get item
