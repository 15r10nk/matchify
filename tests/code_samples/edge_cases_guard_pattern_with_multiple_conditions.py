# before:
DEBUG = True
VERBOSE = False

class Logger:
    pass

log = Logger()
if isinstance(log, Logger) and DEBUG and not VERBOSE:
    print("debug logger")
elif log == None:
    print("none")

# after:
DEBUG = True
VERBOSE = False

class Logger:
    pass

log = Logger()
match log:
    case Logger() if DEBUG and not VERBOSE:
        print("debug logger")
    case None:
        print("none")

# assume:

# trace:
# debug logger
