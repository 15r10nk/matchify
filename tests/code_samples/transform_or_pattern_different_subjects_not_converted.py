# before:
x = 1
y = 2
if x == 1 or y == 2:
    print("match")
elif x == 3:
    print("three")

# after:
x = 1
y = 2
if x == 1 or y == 2:
    print("match")
elif x == 3:
    print("three")

# assume:

# trace:
# match
