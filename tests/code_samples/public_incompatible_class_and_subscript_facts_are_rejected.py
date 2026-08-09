# before:
class First(list): pass
class Second(list): pass
value = First([1])

if isinstance(value, First) and value[0] == 1:
    result = "first"
elif isinstance(value, Second) and value[0] == 2:
    result = "second"
print(result)

# after:
class First(list): pass
class Second(list): pass
value = First([1])

if isinstance(value, First) and value[0] == 1:
    result = "first"
elif isinstance(value, Second) and value[0] == 2:
    result = "second"
print(result)

# assume:

# trace:
# first
