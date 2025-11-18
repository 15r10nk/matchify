<!-- -8<- [start:Header] -->


![ci](https://github.com/15r10nk/matchify/actions/workflows/ci.yml/badge.svg?branch=main)
[![Docs](https://img.shields.io/badge/docs-mkdocs-green)](https://15r10nk.github.io/matchify/)
[![pypi version](https://img.shields.io/pypi/v/matchify.svg)](https://pypi.org/project/matchify/)
![Python Versions](https://img.shields.io/pypi/pyversions/matchify)
![PyPI - Downloads](https://img.shields.io/pypi/dw/matchify)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/15r10nk)](https://github.com/sponsors/15r10nk)

<!-- -8<- [end:Header] -->

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
```

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
elif len(point) == 2:
    print("other pair")

# After
match point:
    case 0, 1:
        print("origin offset")
    case _, _:
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
if len(data) == 2 and len(data[0]) == 2 and data[0][0] == 1 and data[0][1] == 2 and data[1] == 3:
    print("nested list")
elif len(data) == 2 and isinstance(data[0], Point) and len(data[1]) == 2 and data[1][0] == 0 and data[1][1] == 0:
    print("point with coordinates")

# After
match data:
    case [1, 2], 3:
        print("nested list")
    case Point(), [0, 0]:
        print("point with coordinates")
```

<!-- -8<- [start:Feedback] -->
## Issues

If you encounter any problems, please [report an issue](https://github.com/15r10nk/matchify/issues) along with a detailed description.
<!-- -8<- [end:Feedback] -->

## License

Distributed under the terms of the [MIT](http://opensource.org/licenses/MIT) license, "matchify" is free and open source software.
