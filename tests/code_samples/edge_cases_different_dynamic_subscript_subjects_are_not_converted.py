# before:
def classify(items, i, j):
    if items[i] == 1:
        print("i")
    elif items[j] == 2:
        print("j")


classify([1, 2], 0, 1)
classify([0, 2], 0, 1)

# after:
def classify(items, i, j):
    if items[i] == 1:
        print("i")
    elif items[j] == 2:
        print("j")


classify([1, 2], 0, 1)
classify([0, 2], 0, 1)

# assume:

# trace:
# i
# j
