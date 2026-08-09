# before:
def factory(): return 1
value = 1
if value == 1 and value == factory():
    result = "first"
elif value == 2 and value == factory():
    result = "second"
print(result)

# after:
def factory(): return 1
value = 1
if value == 1 and value == factory():
    result = "first"
elif value == 2 and value == factory():
    result = "second"
print(result)

# assume:

# trace:
# first
