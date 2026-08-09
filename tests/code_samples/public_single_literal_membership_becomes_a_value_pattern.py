# before:
value = 1
if value in (1,):
    result = "one"
elif value in (2,):
    result = "two"
print(result)

# after:
value = 1
match value:
    case 1:
        result = "one"
    case 2:
        result = "two"
print(result)

# assume:

# trace:
# one
