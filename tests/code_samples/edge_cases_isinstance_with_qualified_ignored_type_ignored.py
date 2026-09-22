# before:
import typing

value = {"a": "b"}
if isinstance(value, typing.Mapping):
    print("mapping")
elif isinstance(value, str):
    print("string")

other = {"a": "b"}
if isinstance(other, (str, typing.Mapping)):
    print("string or mapping")
elif isinstance(other, bytes):
    print("bytes")

# after:
import typing

value = {"a": "b"}
if isinstance(value, typing.Mapping):
    print("mapping")
elif isinstance(value, str):
    print("string")

other = {"a": "b"}
if isinstance(other, (str, typing.Mapping)):
    print("string or mapping")
elif isinstance(other, bytes):
    print("bytes")

# assume:
# ignore-types: typing\.Mapping

# trace:
# mapping
# string or mapping
