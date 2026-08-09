# before:
class Config:
    def __init__(self, enabled):
        self.enabled = enabled
obj = Config(True)
if isinstance(obj, Config) and obj.enabled is True:
    print("enabled")
elif isinstance(obj, Config) and obj.enabled is False:
    print("disabled")
else:
    print("other")

# after:
class Config:
    def __init__(self, enabled):
        self.enabled = enabled
obj = Config(True)
match obj:
    case Config(enabled=True):
        print("enabled")
    case Config(enabled=False):
        print("disabled")
    case _:
        print("other")

# assume:

# trace:
# enabled
