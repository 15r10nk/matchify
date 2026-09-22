# before:
import os

class FileHandler:
    pass

handler = FileHandler()
if isinstance(handler, FileHandler) and os.path.exists(os.curdir):
    print("handler with file")
elif handler == None:
    print("none")

# after:
import os

class FileHandler:
    pass

handler = FileHandler()
match handler:
    case FileHandler() if os.path.exists(os.curdir):
        print("handler with file")
    case None:
        print("none")

# assume:

# trace:
# handler with file
