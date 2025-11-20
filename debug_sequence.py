import libcst as cst
from matchify.__main__ import IfToMatchTransformer

source = """point = (0, 1)
if len(point) == 2 and point[0] == 0 and point[1] == 1:
    print("origin offset")
elif len(point) == 2 and point[0] == 1 and point[1] == 1:
    print("diagonal")
else:
    print("other")"""

module = cst.parse_module(source)
wrapper = cst.MetadataWrapper(module)
transformed = wrapper.visit(IfToMatchTransformer())
print(transformed.code)
