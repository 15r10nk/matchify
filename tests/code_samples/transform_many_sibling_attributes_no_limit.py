# before:
class Data:
    def __init__(self, a, b, c, d, e, f, g, h, i, j):
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f
        self.g = g
        self.h = h
        self.i = i
        self.j = j
x = Data(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
if isinstance(x, Data) and x.a == 1 and x.b == 2 and x.c == 3 and x.d == 4 and x.e == 5 and x.f == 6 and x.g == 7 and x.h == 8 and x.i == 9 and x.j == 10:
    print("all ten")
elif isinstance(x, Data):
    print("other")

# after:
class Data:
    def __init__(self, a, b, c, d, e, f, g, h, i, j):
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f
        self.g = g
        self.h = h
        self.i = i
        self.j = j
x = Data(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
match x:
    case Data(a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8, i=9, j=10):
        print("all ten")
    case Data():
        print("other")

# assume:

# trace:
# all ten
