# before:
class SimpleCommand:
    pass
command = (1, 2)
if isinstance(command, SimpleCommand):
    print("simple")
elif len(command) == 2:
    print("two")
elif len(command) == 3:
    print("three")

# after:
class SimpleCommand:
    pass
command = (1, 2)
if isinstance(command, SimpleCommand):
    print("simple")
elif len(command) == 2:
    print("two")
elif len(command) == 3:
    print("three")

# assume:

# trace:
# two
