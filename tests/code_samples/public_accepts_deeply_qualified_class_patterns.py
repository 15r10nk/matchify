# before:
class First: pass
class Second: pass
class Models: pass
class Package: pass
package = Package()
package.models = Models()
package.models.First = First
package.models.Second = Second

value = package.models.First()
if isinstance(value, package.models.First):
    result = "first"
elif isinstance(value, package.models.Second):
    result = "second"
print(result)

# after:
class First: pass
class Second: pass
class Models: pass
class Package: pass
package = Package()
package.models = Models()
package.models.First = First
package.models.Second = Second

value = package.models.First()
match value:
    case package.models.First():
        result = "first"
    case package.models.Second():
        result = "second"
print(result)

# assume:

# trace:
# first
