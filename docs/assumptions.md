# Risky assumptions

By default, Matchify enables no risky assumptions. `--safe` makes that explicit,
while `--risky` enables all available risky assumptions. Enable individual
assumptions with a comma-separated list:

```bash
matchify path/to/project/ --assume pure-subjects,use-object
```

`--safe` is conservative, but it is not a formal guarantee that every rewrite
preserves behavior. Python features such as custom equality, descriptors, and
dynamic class behavior can still expose transformer bugs or semantic edge
cases, so review the generated changes and run your project's tests.

When a skipped `if`/`elif` chain would require a risky assumption, the CLI
prints its location and the required `--assume` value instead of converting the
chain.

## `--assume=pure-subjects`

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

## `--assume=use-object`

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

## `--assume=identity-equality`

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

## `--assume=hashable-subjects`

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

## `--assume=list-sequence-pattern`

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

## `--assume=tuple-sequence-pattern`

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

## `--assume=lookup-equality`

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
