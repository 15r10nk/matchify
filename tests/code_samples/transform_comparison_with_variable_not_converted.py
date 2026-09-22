# before:
WIDTH = 100
HEIGHT = 200
x = 100
if x == WIDTH:
    print("matches width")
elif x == HEIGHT:
    print("matches height")
else:
    print("no match")

# after:
WIDTH = 100
HEIGHT = 200
x = 100
if x == WIDTH:
    print("matches width")
elif x == HEIGHT:
    print("matches height")
else:
    print("no match")

# assume:

# trace:
# matches width
