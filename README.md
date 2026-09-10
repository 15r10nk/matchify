<!-- --8<-- [start:Header] -->
# Matchify

![ci](https://github.com/15r10nk/matchify/actions/workflows/ci.yml/badge.svg?branch=main)
[![Docs](https://img.shields.io/badge/docs-mkdocs-green)](https://15r10nk.github.io/matchify/latest/)
[![pypi version](https://img.shields.io/pypi/v/matchify.svg)](https://pypi.org/project/matchify/)
![Python Versions](https://img.shields.io/pypi/pyversions/matchify)
[![PyPI - Downloads](https://img.shields.io/pypi/dw/matchify)](https://pypacktrends.com/?packages=matchify&time_range=2years)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/15r10nk)](https://github.com/sponsors/15r10nk)

Matchify automatically converts eligible `if`/`elif`/`else` chains into
Python 3.10+ `match` statements while preserving runtime behavior and source
formatting.
<!-- --8<-- [end:Header] -->

<!-- --8<-- [start:Feedback] -->
> [!NOTE]
> Matchify was built with assistance from AI tools. Its implementation and
> generated transformations may contain mistakes, so review changes and run
> your project's tests before relying on them. Feedback and bug reports are
> very welcome.
<!-- --8<-- [end:Feedback] -->

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
uvx matchify --write path/to/project/
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

# Convert every eligible chain, including simple two-branch chains
matchify path/to/project/ --all

# Convert with verbose output
matchify --write path/to/project/ -v

# Review diffs without writing changes
matchify path/to/project/ --check

# Show eligible conversions as diffs while converting
matchify path/to/project/ --show --write

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

# Convert only chains that meet a stylistic threshold
matchify path/to/project/ --convert-if "isinstance_checks >= 2 or branches >= 4"
```

`--write` writes conversions and `--check` only reports them as diffs; the two
options cannot be combined. `--check` implies `--show` and exits with 1 if any
file would change. Explicit `--show` or `--show-all` without `--write` is a
preview-only dry run that still exits 0 when conversions are available. In an
interactive terminal, omitting `--write`, `--check`, and the show flags shows a
diff and asks for confirmation before writing. In a non-interactive shell,
choose `--write`, `--check`, or `--show` explicitly.

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

By default, Matchify enables no risky assumptions. `--safe` makes that explicit,
while `--risky` enables all available assumptions. See the
[risky assumptions documentation](https://15r10nk.github.io/matchify/latest/assumptions/)
for the semantic tradeoffs and individual `--assume` names.

`--check` and `--show` review the currently eligible conversions as diffs.
`--show --write` prints the same diffs while converting. Both report how many
conversions were not shown because they need a missing `--assume` value and
point you to `--show-all` to preview them. `--show-all` additionally prints the
required `--assume` value and a separate diff for each group of conversions
unlocked by that assumption.

## Selective conversion with `--convert-if`

By default, Matchify converts every eligible chain. This is equivalent to:

```text
--convert-if True
```

Use `--convert-if` to choose a different threshold based on source and generated
metrics:

```bash
matchify path/to/project/ --convert-if "branches >= 4 and guard_conditions == 0"
```

Use `--all` as an explicit shorthand for the default `--convert-if True`. See the
[selective conversion documentation](https://15r10nk.github.io/matchify/latest/selective-conversion/)
for the expression syntax and complete metric reference.

## Development

Development and repository-testing notes are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## Issues

If you encounter any problems, please [report an issue](https://github.com/15r10nk/matchify/issues) along with a detailed description.

## License

Distributed under the terms of the [MIT](http://opensource.org/licenses/MIT) license, "matchify" is free and open source software.
