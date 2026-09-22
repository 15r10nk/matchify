# before:
option = "-h"
if option in {"-h", "--help"}:
    print("help")
elif option in {"-V", "--version"}:
    print("version")

# after:
option = "-h"
if option in {"-h", "--help"}:
    print("help")
elif option in {"-V", "--version"}:
    print("version")

# assume:
# ignore-types: .*_TYPES$

# trace:
# help
