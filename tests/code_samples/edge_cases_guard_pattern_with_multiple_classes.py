# before:
PRODUCTION = True

class Handler:
    pass

class Worker:
    pass

obj = Handler()
if isinstance(obj, (Handler, Worker)) and PRODUCTION:
    print("production mode")
elif obj == None:
    print("none")

# after:
PRODUCTION = True

class Handler:
    pass

class Worker:
    pass

obj = Handler()
match obj:
    case Handler() | Worker() if PRODUCTION:
        print("production mode")
    case None:
        print("none")

# assume:

# trace:
# production mode
