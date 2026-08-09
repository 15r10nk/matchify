# before:
START = 1
STOP = 2
kind = START
if kind == START:
    print("start")
elif kind == STOP:
    print("stop")

# after:
START = 1
STOP = 2
kind = START
if kind == START:
    print("start")
elif kind == STOP:
    print("stop")

# assume:

# trace:
# start
