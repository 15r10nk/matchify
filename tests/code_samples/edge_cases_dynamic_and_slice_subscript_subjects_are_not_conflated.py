# before:
items = [1, 2]
i = 0
if items[i] == 1:
    print("index")
elif items[0:1] == 2:
    print("slice")

# after:
items = [1, 2]
i = 0
if items[i] == 1:
    print("index")
elif items[0:1] == 2:
    print("slice")

# assume:

# trace:
# index
