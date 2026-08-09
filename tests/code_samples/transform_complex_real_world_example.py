# before:
class Request:
    pass
class Response:
    pass
class Error:
    pass

message = [Request(), 200, "OK"]
if len(message) == 3 and isinstance(message[0], Request) and message[1] == 200 and message[2] == "OK":
    print("success request")
elif len(message) == 3 and isinstance(message[0], Response) and message[1] == 404 and message[2] is None:
    print("not found")
elif len(message) == 3 and isinstance(message[0], Error) and message[1] == 500 and isinstance(message[2], str):
    print("server error")
elif isinstance(message, Request):
    print("plain request")
else:
    print("unknown")

# after:
class Request:
    pass
class Response:
    pass
class Error:
    pass

message = [Request(), 200, "OK"]
match message:
    case Request(), 200, "OK":
        print("success request")
    case Response(), 404, None:
        print("not found")
    case Error(), 500, str():
        print("server error")
    case Request():
        print("plain request")
    case _:
        print("unknown")

# assume:

# trace:
# success request
