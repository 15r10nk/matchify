# before:
option = "-h"
if option in ("-h", "--help"):
    print("help")
elif option in ("-V", "--version"):
    print("version")
else:
    print("other")

# after:
option = "-h"
match option:
    case "-h" | "--help":
        print("help")
    case "-V" | "--version":
        print("version")
    case _:
        print("other")

# assume:

# trace:
# help
