# before:
class Obj:
    status = "ready"
obj = Obj()
if obj.status == "ready":
    print("start")
elif obj.status == "busy":
    print("wait")

# after:
class Obj:
    status = "ready"
obj = Obj()
match obj.status:
    case "ready":
        print("start")
    case "busy":
        print("wait")

# assume:

# trace:
# start
