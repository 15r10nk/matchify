# before:
class ParamSpecType:
    pass

tvar = ParamSpecType()
mapped_arg = ParamSpecType()
if isinstance(tvar, ParamSpecType) and isinstance(mapped_arg, ParamSpecType):
    print("both are ParamSpecType")
elif isinstance(tvar, ParamSpecType):
    print("only tvar")

# after:
class ParamSpecType:
    pass

tvar = ParamSpecType()
mapped_arg = ParamSpecType()
match tvar:
    case ParamSpecType() if isinstance(mapped_arg, ParamSpecType):
        print("both are ParamSpecType")
    case ParamSpecType():
        print("only tvar")

# assume:

# trace:
# both are ParamSpecType
