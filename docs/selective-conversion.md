# Selective conversion

Some projects prefer `match` statements only when a conversion is sufficiently
complex or removes enough repetition. `--convert-if` filters otherwise eligible
`if`/`elif` conversions using metrics from the source chain and the proposed
generated result. Without an explicit option, Matchify uses this filter:

```text
branches >= 3 or isinstance_checks or attribute_checks or sequence_checks
```

This keeps conversions with three or more branches and structurally useful
two-branch conversions, while leaving simple two-branch literal chains alone.
Use `--all` to convert every eligible chain; it is shorthand for
`--convert-if True`.

For example, convert chains that contain at least two `isinstance` checks or at
least four branches:

```bash
matchify path/to/project/ --convert-if "isinstance_checks >= 2 or branches >= 4"
```

Lookup-table conversions are not affected by this option. Matchify first
applies the selected [`--assume` options](assumptions.md), then
evaluates the filter for the proposed `if`/`elif` conversion.

## Expression syntax

Expressions support:

- integer constants and the boolean constants `True` and `False`;
- parentheses;
- arithmetic with `+`, `-`, `*`, and `/`;
- `and`, `or`, and `not`;
- `<`, `<=`, `==`, `!=`, `>=`, and `>`.

Metric values use normal integer truthiness: zero is false and a nonzero value
is true. For example, this converts chains with at least three branches only
when no conditions remain in guards:

```bash
matchify path/to/project/ --convert-if "branches >= 3 and not guard_conditions"
```

`--convert-if` may be specified only once. Combine multiple criteria in one
expression with `and` and `or`. It cannot be combined with `--all`.

Arithmetic uses normal Python precedence and `/` performs true division.
Expressions are parsed as a restricted syntax tree and are never passed to
`eval()`. Function calls, attribute access, subscripts, other arithmetic
operators, strings, and unknown variables are rejected before any files are
processed.

## Source metrics

These values describe the original `if`/`elif` chain:

### `branches`

The number of `if`/`elif` branches, excluding `else`. This example has
`branches == 3`:

``` python
# Before
if status == 200:
    handle_success()
elif status == 404:
    handle_missing()
elif status == 500:
    handle_error()
else:
    handle_other()

# After: matchify --convert-if "branches == 3"
match status:
    case 200:
        handle_success()
    case 404:
        handle_missing()
    case 500:
        handle_error()
    case _:
        handle_other()
```

### `isinstance_checks`

The number of recognized `isinstance(...)` checks. Each call counts once,
even when its class information contains multiple types. This example has
`isinstance_checks == 2`:

```python
# Before
if isinstance(value, str):
    handle_text()
elif isinstance(value, (int, float)):
    handle_number()

# After: matchify --convert-if "isinstance_checks == 2"
match value:
    case str():
        handle_text()
    case int() | float():
        handle_number()
```

### `literal_checks`

The number of recognized literal or singleton alternatives. Every value in a
recognized membership test counts separately. This example has
`literal_checks == 3`:

```python
# Before
if command in ("start", "run"):
    launch()
elif command == "stop":
    stop()

# After: matchify --convert-if "literal_checks == 3"
match command:
    case "start" | "run":
        launch()
    case "stop":
        stop()
```

### `attribute_checks`

The number of recognized conditions whose subject path inspects at least one
attribute. It counts conditions, not individual dots in a path. This example
has `attribute_checks == 2`:

```python
# Before
if isinstance(node, Point) and node.x == 1:
    handle_one()
elif isinstance(node, Point) and node.x == 2:
    handle_two()

# After: matchify --convert-if "attribute_checks == 2"
match node:
    case Point(x=1):
        handle_one()
    case Point(x=2):
        handle_two()
```

### `sequence_checks`

The number of recognized sequence length checks. This example has
`sequence_checks == 2` because each branch contains one `len(data) == 2`
condition:

```python
# Before
if len(data) == 2 and data[0] == "x":
    handle_x()
elif len(data) == 2 and data[0] == "y":
    handle_y()

# After: matchify --convert-if "sequence_checks == 2"
match data:
    case "x", _:
        handle_x()
    case "y", _:
        handle_y()
```

### `max_depth`

The greatest attribute/subscript depth of any recognized check. A direct name
has depth 0; each attribute or subscript adds one. This example has
`max_depth == 2` because `node.position.x` is two levels below `node`:

```python
# Before
if (
    isinstance(node, Point)
    and isinstance(node.position, Position)
    and node.position.x == 1
):
    handle_one()
elif (
    isinstance(node, Point)
    and isinstance(node.position, Position)
    and node.position.x == 2
):
    handle_two()

# After: matchify --convert-if "max_depth == 2"
match node:
    case Point(position=Position(x=1)):
        handle_one()
    case Point(position=Position(x=2)):
        handle_two()
```

## Generated-result metrics

These values describe the proposed `match` statement after Matchify has
compiled it:

### `patterns`

The number of generated cases with a structural pattern. A wildcard `case _`
does not count. This example has `patterns == 2`:

```python
# Before
if value == 1:
    handle_one()
elif value == 2:
    handle_two()
else:
    handle_other()

# After: matchify --convert-if "patterns == 2"
match value:
    case 1:
        handle_one()
    case 2:
        handle_two()
    case _:
        handle_other()
```

### `guard_conditions`

The number of individual conditions retained in generated guards. Conditions
joined with `and` count separately. This example has `guard_conditions == 4`:

```python
# Before
if value == 1 and enabled and ready:
    handle_one()
elif value == 2 and enabled and ready:
    handle_two()

# After: matchify --convert-if "guard_conditions == 4"
match value:
    case 1 if enabled and ready:
        handle_one()
    case 2 if enabled and ready:
        handle_two()
```

### `captures`

The number of names bound by generated capture patterns. This example has
`captures == 2`, one generated capture in each case:

```python
# Before
if len(data) == 2 and data[0] == "x":
    result = data[1]
    print(result)
elif len(data) == 2 and data[0] == "y":
    result = data[1]
    print(result)

# After: matchify --convert-if "captures == 2"
match data:
    case "x", result:
        print(result)
    case "y", result:
        print(result)
```

This distinction makes it possible to filter using both the shape of the input
and the readability of the result:

```bash
matchify path/to/project/ \
  --convert-if "branches >= 3 and patterns >= 2 and guard_conditions <= 1"
```

## Rejected conversions

When an otherwise valid conversion does not match the expression, Matchify
leaves that chain unchanged. Rejections are silent by default. Use `--verbose`
to report their source locations:

```bash
matchify path/to/project/ --verbose --convert-if "branches >= 4"
```

## Interaction with assumptions

Matchify resolves `--safe`, `--risky`, and `--assume` before evaluating the
filter. The metrics therefore describe the conversion permitted by the selected
assumptions. The filter is a stylistic preference; it does not enable a
conversion that would otherwise be rejected for safety reasons.
