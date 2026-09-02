# Matchify

![ci](https://github.com/15r10nk/matchify/actions/workflows/ci.yml/badge.svg?branch=main)

[![pypi version](https://img.shields.io/pypi/v/matchify.svg)](https://pypi.org/project/matchify/)
![Python Versions](https://img.shields.io/pypi/pyversions/matchify)
[![PyPI - Downloads](https://img.shields.io/pypi/dw/matchify)](https://pypacktrends.com/?packages=matchify&time_range=2years)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/15r10nk)](https://github.com/sponsors/15r10nk)

Matchify automatically converts eligible `if`/`elif`/`else` chains into
Python 3.10+ `match` statements while preserving runtime behavior and source
formatting.

> [!NOTE]
> Matchify was built with assistance from AI tools. Its implementation and
> generated transformations may contain mistakes, so review changes and run
> your project's tests before relying on them. Feedback and bug reports are
> very welcome.

## Examples

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

## Installation

Install "matchify" as a command-line tool with
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install matchify
```

Or run it without installing:

```bash
uvx matchify path/to/project/
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
matchify --write path/to/file.py

# Convert all Python files in a directory
matchify --write path/to/project/

# Convert with verbose output
matchify --write path/to/project/ -v

# Check whether files would be converted without writing changes
matchify path/to/project/ --check

# Show eligible conversions as diffs while converting
matchify path/to/project/ --show --write

# Review diffs without writing changes
matchify path/to/project/ --show --check

# Also preview conversions that need a missing --assume value
matchify path/to/project/ --show-all --check

# Use parallel processing (default: number of CPUs)
matchify path/to/project/ --write -j 8

# Enable one risky assumption explicitly
matchify path/to/project/ --write --assume pure-subjects

# Disable all risky assumptions
matchify path/to/project/ --write --safe

# Enable all risky assumptions
matchify path/to/project/ --write --risky
```

`--write` writes conversions and `--check` only reports them; the two options
cannot be combined. In an interactive terminal, omitting both shows a diff and
asks for confirmation before writing. In a non-interactive shell, choose either
`--write` or `--check` explicitly.

## pre-commit

Matchify provides two pre-commit hooks.

Use `matchify` to automatically rewrite files, similar to the default Black
hook:

```yaml
repos:
- repo: https://github.com/15r10nk/matchify
  rev: v0.1.0
  hooks:
  - id: matchify
```

Use `matchify-check` to only report files that would be converted without
modifying them:

```yaml
repos:
- repo: https://github.com/15r10nk/matchify
  rev: v0.1.0
  hooks:
  - id: matchify-check
```

## Risky assumptions

By default, Matchify enables no risky assumptions. `--safe` makes that explicit.
`--risky` enables all available risky assumptions.
`--safe` is conservative, but it is not a formal guarantee that every rewrite
preserves behavior. Python features such as custom equality, descriptors, and
dynamic class behavior can still expose transformer bugs or semantic edge
cases, so review the generated changes and run your project's tests.
When a skipped `if`/`elif` chain would require a risky assumption, the CLI
prints the file location and the required `--assume` value instead of converting
that chain.

Use `--show` to review the currently eligible conversions as diffs.
Combine it with `--check` to review without writing files. `--show` also reports
how many conversions were not shown because they need a missing `--assume` value
and points you to `--show-all` to preview them. `--show-all` additionally
prints the required `--assume` value and a separate diff for each group of
conversions unlocked by that assumption.

### `--assume=pure-subjects`

Permits transformations such as `a.x == 1 and b.y == 2` into a match on
`(a.x, b.y)`. This evaluates every subject eagerly, so enable it only when those
name, attribute, and subscript reads cannot raise exceptions or produce
observable side effects. Without the option, later `and` operands remain guards
and preserve short-circuiting.

```python
# Before
if a.x == 1 and b.y == 2:
    handle_first()
elif a.x == 3 and b.y == 4:
    handle_second()

# After
match (a.x, b.y):
    case 1, 2:
        handle_first()
    case 3, 4:
        handle_second()
```

### `--assume=use-object`

Permits generic attribute patterns such as `object(x=1)` when different
branches inspect attributes of a common object without an explicit `isinstance`
check. This performs pattern-time attribute lookups, so enable it only when
those lookups cannot raise exceptions or produce observable side effects.

```python
# Before
if value.x == 1:
    handle_x()
elif value.y == 2:
    handle_y()

# After
match value:
    case object(x=1):
        handle_x()
    case object(y=2):
        handle_y()
```

### `--assume=identity-equality`

Permits conversions from qualified identity comparisons such as
`op is Op.ADD` to value patterns such as `case Op.ADD`. Match value patterns
compare with equality, not identity, so enable it only when identity and
equality are equivalent for those values.

```python
# Before
if op is Op.ADD:
    add()
elif op is Op.SUB:
    subtract()

# After
match op:
    case Op.ADD:
        add()
    case Op.SUB:
        subtract()
```

### `--assume=hashable-subjects`

Permits membership tests against literal sets to become OR patterns. Set
membership hashes the subject and can raise `TypeError` for an unhashable value,
while a pattern only performs equality comparisons. Enable it only when match
subjects are hashable. Custom `__hash__` and `__eq__` implementations may still
make lookup behavior or side effects differ from pattern matching.

```python
# Before
if value in {1, 2}:
    handle_small()
elif value == 3:
    handle_three()

# After
match value:
    case 1 | 2:
        handle_small()
    case 3:
        handle_three()
```

### `--assume=list-sequence-pattern`

Permits a sequence pattern to imply an explicit `isinstance(value, list)`
check. Python sequence patterns can also match other sequence types, so enable
it only when that broader match is acceptable.

```python
# Before
if isinstance(value, list) and len(value) == 1 and value[0] == 1:
    handle_one()
elif value is None:
    handle_none()

# After
match value:
    case 1,:
        handle_one()
    case None:
        handle_none()
```

### `--assume=tuple-sequence-pattern`

Permits a sequence pattern to imply an explicit `isinstance(value, tuple)`
check. Python sequence patterns can also match other sequence types, so enable
it only when that broader match is acceptable. Checks against `(list, tuple)`
require both sequence assumptions.

```python
# Before
if isinstance(value, tuple) and len(value) == 1 and value[0] == 1:
    handle_one()
elif value is None:
    handle_none()

# After
match value:
    case 1,:
        handle_one()
    case None:
        handle_none()
```

### `--assume=lookup-equality`

Permits dictionary lookup tables embedded in statements to become `match`
statements. Dictionary lookup uses hashing while patterns use equality, and
dictionary values are evaluated only in the selected case instead of eagerly
when constructing the dictionary. Enable it only when those equality and
evaluation-order differences are acceptable. Tuple keys, including nested
tuples, become sequence patterns and can therefore also match equivalent
non-tuple sequences.

```python
# Before
result = {"create": "POST", "read": "GET"}[operation]

# After
match operation:
    case "create":
        result = "POST"
    case "read":
        result = "GET"
    case _matchify_key:
        raise KeyError(_matchify_key)
```

## Development

Development and repository-testing notes are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Issues

If you encounter any problems, please [report an issue](https://github.com/15r10nk/matchify/issues) along with a detailed description.

## License

Distributed under the terms of the [MIT](http://opensource.org/licenses/MIT) license, "matchify" is free and open source software.
