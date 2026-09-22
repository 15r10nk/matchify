# before:
option = "-h"
if option in {"-h", "--help"}:
    print("help")
elif option in {"-V", "--version"}:
    print("version")

# after:
option = "-h"
match option:
    case "-h" | "--help":
        print("help")
    case "-V" | "--version":
        print("version")

# assume: hashable-subjects
# ignore-types: .*_TYPES$

# trace:
# help
