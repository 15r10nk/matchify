# before:
class Value(int):
    def __getitem__(self, index): return (1, 2)[index]
value = Value(3)
if (value[0] == 1 or value[1] == 2) and value == 3:
    result = "three"
elif value == 4:
    result = "four"
print(result)

# after:
class Value(int):
    def __getitem__(self, index): return (1, 2)[index]
value = Value(3)
match value:
    case 3 if (value[0] == 1 or value[1] == 2):
        result = "three"
    case 4:
        result = "four"
print(result)

# assume:

# trace:
# three
