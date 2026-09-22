# before:
value = 2
first_flag = False
second_flag = True

if (value == 1 and first_flag) or (value == 2 and second_flag):
    result = "flagged"
elif value == 3:
    result = "three"
print(result)

# after:
value = 2
first_flag = False
second_flag = True

match value:
    case _ if (value == 1 and first_flag) or (value == 2 and second_flag):
        result = "flagged"
    case 3:
        result = "three"
print(result)

# assume:

# trace:
# flagged
