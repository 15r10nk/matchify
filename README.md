![ci](https://github.com/15r10nk/matchify/actions/workflows/ci.yml/badge.svg?branch=main)
[![pypi version](https://img.shields.io/pypi/v/matchify.svg)](https://pypi.org/project/matchify/)
![Python Versions](https://img.shields.io/pypi/pyversions/matchify)
![PyPI - Downloads](https://img.shields.io/pypi/dw/matchify)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/15r10nk)](https://github.com/sponsors/15r10nk)

## Installation

You can install "matchify" via [pip](https://pypi.org/project/pip/):

``` bash
pip install matchify
```

## Key Features

- **Automatic conversion** of if/elif/else chains to Python 3.10+ match statements
- **Preserves formatting** and code structure using LibCST
- **Supports multiple pattern types**:
  - Literal comparisons (`x == 1`, `x == "value"`)
  - Identity checks (`x is None`, `x is True`)
  - isinstance checks (`isinstance(x, MyClass)`)
  - Class patterns with attributes (`isinstance(p, Point) and p.x == 5`)
  - Sequence patterns (`len(x) == 2 and x[0] == 0 and x[1] == 1`)
  - Nested sequences (`[[1, 2], 3]`)
  - Sequence attributes in class patterns (`Data(value=[1, 2, 3])`)
  - Or patterns for isinstance tuples (`isinstance(x, (int, float))`)
- **Parallel processing** for fast conversion of large codebases
- **Safe transformations** - only converts when semantics are preserved

## Usage

```bash
# Convert a single file
matchify path/to/file.py

# Convert all Python files in a directory
matchify path/to/project/

# Convert with verbose output
matchify path/to/project/ -v

# Use parallel processing (default: number of CPUs)
matchify path/to/project/ -j 8

# Enable one risky assumption explicitly
matchify path/to/project/ --assume pure-subjects

# Disable all risky assumptions
matchify path/to/project/ --safe

# Enable all risky assumptions
matchify path/to/project/ --risky
```

By default, Matchify enables no risky assumptions. `--safe` makes that explicit.
`--risky` enables all available risky assumptions.
When a skipped `if`/`elif` chain would require a risky assumption, the CLI
prints the file location and the required `--assume` value instead of converting
that chain.

Available risky assumptions:

- `pure-subjects`: permits transformations such as
  `a.x == 1 and b.y == 2` into a match on `(a.x, b.y)`. This evaluates every
  subject eagerly, so enable it only when those name, attribute, and subscript
  reads cannot raise exceptions or produce observable side effects. Without the
  option, later `and` operands remain guards and preserve short-circuiting.
- `use-object`: permits generic attribute patterns such as `object(x=1)` when
  different branches inspect attributes of a common object without an explicit
  `isinstance` check. This performs pattern-time attribute lookups, so enable it
  only when those lookups cannot raise exceptions or produce observable side
  effects.

## Testing against external repositories

`test-repos.py` clones the projects configured in `test-repos.json`, prepares
their test environments, runs a baseline test suite, applies the local
Matchify checkout, validates changed files with the project's Python
interpreter, and reruns the tests.

Run one configured repository:

```bash
uv run python test-repos.py django-rest-framework \
  --workspace /tmp/matchify-drf
```

Run every configured repository or list the available names:

```bash
uv run python test-repos.py --workspace /tmp/matchify-repos
uv run python test-repos.py --list
```

The workspace must be new. Each repository gets isolated clone, setup, test,
Matchify, and syntax logs. A combined `summary.json` is written at the
workspace root. Use `--skip-baseline` to omit the initial test run or
`--skip-tests` to perform setup, conversion, and syntax validation only.

Repository entries may configure `url`, `ref`, clone arguments, source and
excluded paths, extra Matchify arguments, setup commands, the target Python
command, the test command, environment variables, batch size, and timeout.
The `{root}`, `{repo}`, and `{workspace}` placeholders are available in
commands and environment values.

### Examples

**Simple equality chain:**
```python
# Before
if x == 1:
    print("one")
elif x == 2:
    print("two")
else:
    print("other")

# After
match x:
    case 1:
        print("one")
    case 2:
        print("two")
    case _:
        print("other")
```

**isinstance with attributes:**
```python
# Before
if isinstance(node, Point) and node.x == 5:
    print("x is 5")
elif isinstance(node, Point):
    print("other point")

# After
match node:
    case Point(x=5):
        print("x is 5")
    case Point():
        print("other point")
```

**Sequence patterns:**
```python
# Before
if len(point) == 2 and point[0] == 0 and point[1] == 1:
    print("origin offset")
elif len(point) == 2 and point[0] == 1:
    print("other pair")

# After
match point:
    case 0, 1:
        print("origin offset")
    case 1, _:
        print("other pair")
```

**Nested patterns (isinstance inside sequences):**
```python
# Before
if len(x) == 2 and isinstance(x[0], Point) and x[1] == 2:
    print("point and 2")
elif len(x) == 2 and x[0] == 1 and x[1] == 1:
    print("ones")

# After
match x:
    case Point(), 2:
        print("point and 2")
    case 1, 1:
        print("ones")
```

**Nested sequences:**
```python
# Before
if (
    len(data) == 2
    and len(data[0]) == 2
    and data[0][0] == 1
    and data[0][1] == 2
    and data[1] == 3
):
    print("nested list")
elif (
    len(data) == 2
    and isinstance(data[0], Point)
    and len(data[1]) == 2
    and data[1][0] == 0
    and data[1][1] == 0
):
    print("point with coordinates")

# After
match data:
    case [1, 2], 3:
        print("nested list")
    case Point(), [0, 0]:
        print("point with coordinates")
```

**Class patterns with sequence attributes:**
```python
# Before
class Data:
    def __init__(self, value):
        self.value = value


obj = Data([1, 2, 3])
if (
    isinstance(obj, Data)
    and len(obj.value) == 3
    and obj.value[0] == 1
    and obj.value[1] == 2
    and obj.value[2] == 3
):
    print("data with list")
elif isinstance(obj, Data):
    print("other data")


# After
class Data:
    def __init__(self, value):
        self.value = value


obj = Data([1, 2, 3])
match obj:
    case Data(value=[1, 2, 3]):
        print("data with list")
    case Data():
        print("other data")
```

## Issues

If you encounter any problems, please [report an issue](https://github.com/15r10nk/matchify/issues) along with a detailed description.

## License

Distributed under the terms of the [MIT](http://opensource.org/licenses/MIT) license, "matchify" is free and open source software.
