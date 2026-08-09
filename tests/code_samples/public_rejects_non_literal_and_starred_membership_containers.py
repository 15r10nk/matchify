# before:
values = (1, 2)
value = 1
if value in values:
    result = "dynamic"
elif value == 3:
    result = "literal fallback"
print(result)

if value in (*values,):
    result = "starred"
elif value == 3:
    result = "literal fallback"
print(result)

# after:
values = (1, 2)
value = 1
if value in values:
    result = "dynamic"
elif value == 3:
    result = "literal fallback"
print(result)

if value in (*values,):
    result = "starred"
elif value == 3:
    result = "literal fallback"
print(result)

# assume:

# trace:
# dynamic
# starred
