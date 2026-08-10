# before:
color = "red"
if color == "red":
    print("Red")
    value = 1
elif color == "blue":
    print("Blue")
    value = 2
else:
    print("Unknown")
    value = 0
print(f"Value: {value}")

# after:
color = "red"
match color:
    case "red":
        print("Red")
        value = 1
    case "blue":
        print("Blue")
        value = 2
    case _:
        print("Unknown")
        value = 0
print(f"Value: {value}")

# assume:

# trace:
# Red
# Value: 1
