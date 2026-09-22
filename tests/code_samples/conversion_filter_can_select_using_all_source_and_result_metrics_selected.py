# before:
class Point:
    pass

value = Point()
value.x = 1

if isinstance(value, Point) and value.x == 1:
    print("one")
elif isinstance(value, Point) and value.x == 2:
    print("two")

# after:
class Point:
    pass

value = Point()
value.x = 1

match value:
    case Point(x=1):
        print("one")
    case Point(x=2):
        print("two")

# assume:
# convert-if: branches == 2 and isinstance_checks == 2 and literal_checks == 2 and attribute_checks == 2 and sequence_checks == 0 and max_depth == 1 and patterns == 2 and pattern_nodes == 4 and value_patterns == 0 and self_value_patterns == 0 and class_patterns == 2 and sequence_patterns == 0 and or_alternatives == 0 and max_pattern_depth == 2 and guarded_cases == 0 and guard_conditions == 0 and captures == 0

# trace:
# one
