# before:
color = "red"
if color == "red" or color == "green" or color == "blue":
    print("primary color")
elif color == "yellow" or color == "cyan" or color == "magenta":
    print("secondary color")

# after:
color = "red"
match color:
    case "red" | "green" | "blue":
        print("primary color")
    case "yellow" | "cyan" | "magenta":
        print("secondary color")

# assume:

# trace:
# primary color
