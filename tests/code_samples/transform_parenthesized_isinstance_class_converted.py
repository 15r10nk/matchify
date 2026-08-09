# before:
class SomeClass:
    pass

value = SomeClass()
if isinstance(value, (SomeClass)):
    print("some")
elif isinstance(value, str):
    print("string")

# after:
class SomeClass:
    pass

value = SomeClass()
match value:
    case SomeClass():
        print("some")
    case str():
        print("string")

# assume:

# trace:
# some
