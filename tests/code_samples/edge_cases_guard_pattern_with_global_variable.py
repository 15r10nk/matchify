# before:
ENABLED = True

class Config:
    pass

cfg = Config()
if isinstance(cfg, Config) and ENABLED:
    print("enabled config")
elif cfg == None:
    print("none")

# after:
ENABLED = True

class Config:
    pass

cfg = Config()
match cfg:
    case Config() if ENABLED:
        print("enabled config")
    case None:
        print("none")

# assume:

# trace:
# enabled config
