# before:
rgb = (255, 0, 0)
if len(rgb) == 3 and rgb[0] == 255 and rgb[1] == 0 and rgb[2] == 0:
    print("red")
elif len(rgb) == 3 and rgb[0] == 0 and rgb[1] == 255 and rgb[2] == 0:
    print("green")
else:
    print("other")

# after:
rgb = (255, 0, 0)
match rgb:
    case 255, 0, 0:
        print("red")
    case 0, 255, 0:
        print("green")
    case _:
        print("other")

# assume:

# trace:
# red
