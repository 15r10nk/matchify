"""Example demonstrating star pattern support in matchify."""

# Before: Using >= operator with length checks
data = [1, 2, 3, 4, 5]
match data:
    case 1, 2, *_:
        print("starts with 1, 2")
    case 0, *_:
        print("starts with 0")
    case _:
        print("other")

# After running matchify, this becomes:
# match data:
#     case 1, 2, *_:
#         print("starts with 1, 2")
#     case 0, *_:
#         print("starts with 0")
#     case _:
#         print("other")

# Works with isinstance too
class Point:
    pass

points = [Point(), 1, 2, 3]
match points:
    case Point(), 1, *_:
        print("point then 1, with more items")
    case Point(), *_:
        print("starts with point, with more items")

# Becomes:
# match points:
#     case Point(), 1, *_:
#         print("point then 1, with more items")
#     case Point(), *_:
#         print("starts with point, with more items")
