# before:
marker = 1
value = marker
if value == 1 and value is marker:
    result = "first"
elif value == 2 and value is marker:
    result = "second"
print(result)

# after:
marker = 1
value = marker
if value == 1 and value is marker:
    result = "first"
elif value == 2 and value is marker:
    result = "second"
print(result)

# assume:

# trace:
# first
