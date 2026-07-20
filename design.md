# Matchify Design Direction

## Goal

Matchify should convert `if`/`elif`/`else` chains into `match` statements by
first preserving the logical structure of each branch condition, then gradually
lowering safe predicates into match patterns.

The intended pipeline is:

```text
Python condition
-> boolean condition tree
-> predicates on subject paths
-> pattern tree plus residual conditions
-> match case with optional guard
```

This keeps recognition, safety checks, pattern construction, and guard rendering
separate.

## Boolean Condition Tree

Each branch condition should first be parsed into a small logical IR:

```text
BoolExpr =
    And(BoolExpr...)
  | Or(BoolExpr...)
  | Predicate(...)
```

Predicates should be concrete typed nodes. Avoid a generic `kind` field with an
unstructured payload; that would just move stringly-typed dispatch into the IR.
Each predicate type should expose only the fields that are meaningful for that
predicate.

```text
Predicate =
    IsInstancePredicate(path, classes, original)
  | LenEqualsPredicate(path, length, original)
  | LenAtLeastPredicate(path, minimum, original)
  | EqualsPredicate(path, value, original)
  | IsPredicate(path, value, original)
  | RawPredicate(original)
```

Examples:

```text
isinstance(value, Point)
```

becomes:

```text
IsInstancePredicate(path=subject, classes=(Point,))
```

```text
value.x == 1
```

becomes:

```text
EqualsPredicate(path=subject.x, value=1)
```

Unrecognized expressions remain raw predicates and can later become guard
conditions.

Predicate paths are initially absolute `AccessPath` values. For example,
`value.child.kind` is represented by a `NameRoot("value")` followed by two
attribute parts. After all branches have been parsed, the compiler selects a
common subject prefix and replaces that prefix with `MatchSubjectRoot()`.
For an eagerly evaluated composite subject, each selected path is additionally
prefixed with a synthetic `SubscriptPathPart` describing its tuple slot. Paths
outside the selected subject plan keep their original root and remain eligible
for residual guards.

For example, the subject plan for `(a.x, b.y)` binds paths as follows:

```text
a.x.value -> MatchSubjectRoot(), SubscriptPathPart(0), AttributePathPart("value")
b.y.kind  -> MatchSubjectRoot(), SubscriptPathPart(1), AttributePathPart("kind")
```

By default, composite subjects are selected only from conditions that already
evaluate all components eagerly, such as explicit tuple comparisons. An `and`
condition continues to use one subject plus residual guards so its
short-circuit behavior is preserved. When `assume_pure_subjects` is enabled,
the compiler may also combine the branch-stable subjects of `and` conditions;
the caller then explicitly accepts their eager evaluation.

## Pattern Anchors

Not every predicate can safely become a pattern by itself. Some predicates only
become pattern-compatible after another predicate proves the shape of the value.

The main anchors are:

- `isinstance(subject_path, Class)` creates a class pattern anchor.
- `len(subject_path) == n` creates a fixed sequence pattern anchor.
- `len(subject_path) >= n` creates a star sequence pattern anchor.

Once an anchor exists, related predicates below the same path can be inserted
into the pattern tree.

Example:

```text
if isinstance(value, Point) and value.x == 1 and enabled:
```

can become:

```text
Pattern: Point(x=1)
Residual: enabled
```

and finally:

```text
case Point(x=1) if enabled:
```

Without a type anchor, an attribute predicate such as `value.x == 1` should not
be treated as a class pattern by itself.

## Recursive Pattern Builder

Pattern construction should be recursive. A matcher should receive a piece of
the `BoolExpr` tree and try to produce a pattern node for the current subject
path.

```text
build_pattern(expr, root_path) -> PatternBuildResult
```

The result contains:

```text
PatternBuildResult:
  pattern: PatternNode | None
  residual: BoolExpr | None
```

Anchors create pattern nodes:

- `IsInstancePredicate(path=subject, class=Point)` creates `ClassPattern(Point)`.
- `LenEqualsPredicate(path=subject, length=2)` creates a fixed
  `SequencePattern`.
- `LenAtLeastPredicate(path=subject, minimum=2)` creates a star
  `SequencePattern`.

After an anchor exists, predicates below the same path are inserted recursively
into that node.

Example:

```text
if (
    isinstance(value, Point)
    and value.x == 1
    and isinstance(value.child, Node)
    and value.child.kind == "ready"
):
```

becomes:

```text
ClassPattern(
  Point,
  attrs={
    x: ValuePattern(1),
    child: ClassPattern(
      Node,
      attrs={
        kind: ValuePattern("ready")
      }
    )
  }
)
```

The bound `AccessPath` decides where a predicate belongs. A predicate for
`subject.child.kind` is inserted into the `child` attribute, then recursively
into the `kind` attribute of the nested pattern.

The builder must not invent class or sequence nodes without anchors. For
example, `value.x == 1` alone remains a residual condition because no predicate
has proven that `value` can safely be matched as a class pattern.

## AND Handling

`And(...)` combines compatible predicates into one pattern result.

Pattern-capable predicates are consumed into the pattern tree. Predicates that
cannot be safely represented as patterns remain as residual conditions.

Example:

```text
if isinstance(value, Point) and value.x == 1 and value.ready():
```

becomes:

```text
Pattern: Point(x=1)
Residual: value.ready()
```

and renders as:

```text
case Point(x=1) if value.ready():
```

For nested attributes, `And(...)` still means "insert all compatible constraints
into the same pattern tree":

```text
if isinstance(value, Point) and (value.x == 1 or value.x == 2):
```

can become:

```text
ClassPattern(
  Point,
  attrs={
    x: OrPattern(ValuePattern(1), ValuePattern(2))
  }
)
```

## OR Handling

`Or(...)` should normalize each alternative independently.

Simple alternatives without residual conditions can become a match OR pattern:

```text
if value == 1 or value == 2:
```

```text
case 1 | 2:
```

Alternatives with the same residual condition may share one guard:

```text
if (value == 1 and enabled) or (value == 2 and enabled):
```

```text
case 1 | 2 if enabled:
```

Alternatives with different residual conditions must not be merged into one OR
pattern, because Python guards apply to the whole case, not to individual
alternatives.

This is unsafe:

```text
if (isinstance(value, Point) and value.ready()) or isinstance(value, Token):
```

It must not become:

```text
case Point() | Token() if value.ready():
```

because that changes the meaning for `Token`.

The algorithm must therefore validate OR results before rendering:

- all OR alternatives may have no residual condition, or
- all OR alternatives may have an equivalent residual condition, or
- the conversion must be rejected for that branch.

## Residual Conditions

Residual conditions are predicates that were not consumed into the pattern tree.
They render as the `if` guard of the generated `case`.

For non-OR patterns, this is straightforward:

```text
Pattern: Point(x=1)
Residual: enabled and value.ready()
```

renders as:

```text
case Point(x=1) if enabled and value.ready():
```

For OR patterns, residual conditions need the stricter validation described
above.

## Suggested Result Types

A useful intermediate result could look like:

```text
NormalizedBranch:
  pattern: PatternNode | None
  residual: BoolExpr | None
```

For OR alternatives:

```text
AlternativeResult:
  pattern: PatternNode
  residual: BoolExpr | None
```

The compiler should only render a branch when the normalized result is safe.
Otherwise, it should either keep the original `if` chain unchanged or fall back
to a conservative guard-only case when that preserves semantics.

## Expected Benefits

- Fewer special-case recognizers for concrete Python syntax combinations.
- Cleaner handling of nested `and`/`or` conditions.
- Better separation between logical analysis and pattern rendering.
- Safer guard behavior, especially around OR patterns.
- Easier future support for more predicate types.

The core principle is: consume only predicates that are proven safe as match
patterns; keep everything else as explicit residual conditions.
