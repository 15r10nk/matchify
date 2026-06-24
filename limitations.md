# Matchify Limitations

Matchify only rewrites an `if`/`elif` chain when it can preserve semantics. When a
condition is unsupported or ambiguous, the transformer either keeps the original
`if` chain or emits a `case _ if ...` guard instead of forcing an unsafe pattern.

## Chains That Are Not Converted

- Single `if` statements without an `elif` are not converted.
- Branches must describe the same match subject. Chains that compare or inspect
  unrelated subjects are left unchanged.
- Conditions must be safe to evaluate as a match statement. Unsupported or
  order-sensitive expressions prevent conversion.
- Non-equality comparisons such as `>`, `<`, `>=`, `<=`, and `!=` are not moved
  into patterns. They may remain as guards when the rest of the branch has a
  recognizable pattern.

## Value and OR Patterns

- Matchify only turns literals and singletons into value patterns.
- Comparisons against variables are not converted into value patterns because a
  bare name in a `case` pattern would bind a new variable instead of comparing
  with the existing value.
- Comparisons against f-strings are not converted into value patterns because
  Python does not allow f-strings in `case` value patterns. They can still be
  preserved as guards around a surrounding class or sequence pattern.
- OR patterns must describe the same subject in every alternative.
- OR patterns support literal/singleton comparisons, plain `isinstance`
  alternatives such as `x == 1 or isinstance(x, Point)`, and alternatives whose
  nested class attribute or sequence checks can be moved fully into patterns.
- OR alternatives that need their own guards, such as
  `(isinstance(x, Point) and x.kind > 0) or isinstance(x, Token)`, are not folded
  into one OR pattern because Python only supports guards for the whole `case`.
- Generated safe traces keep sequence-type guards such as
  `isinstance(x.items, (list, tuple))` out of random OR alternatives because those
  guards apply to only one alternative. Hand-written OR alternatives without that
  extra guard can still fold to patterns such as `Point(items=[1, None]) | 0`.

## Class Patterns

- `isinstance` checks with ignored type placeholders such as `*_TYPES` are not
  converted by default.
- A walrus expression in the `isinstance` subject position, for example
  `isinstance((x := make()), Point)`, is not converted because the assignment
  cannot be preserved safely by a pattern.

## Sequence Patterns

- Sequence patterns require a `len(...)` check for the sequence being matched.
- Matchify allows gaps in checked sequence indices by inserting `_` wildcards,
  but three or more consecutive wildcard positions prevent conversion.
- Open-ended sequence checks are only converted for recognized star-pattern
  shapes such as `len(x) >= 2 and x[0] == 1 and x[1] == 2`.
- Nested sequence patterns also need their own nested `len(...)` checks.

## Guards

- Conditions that are not part of the match subject are preserved as guards.
- Boolean conditions, non-equality comparisons, walrus-based checks outside the
  match subject, and additional `isinstance` checks on other variables are guard
  candidates.
- Comparisons against variables can be preserved as guards when a surrounding
  literal/class/sequence pattern still identifies the match subject.
- Non-literal comparisons on nested subject attributes, including attributes of
  class patterns inside sequence elements, stay as guards instead of being moved
  into patterns.
- Unsupported checks that originate inside nested attributes or sequence
  elements are emitted as case-level guards; Python patterns do not support a
  separate guard attached to only that nested subpattern.
- Guards intentionally preserve unsupported fragments instead of dropping them.
  This means the generated `match` statement can be correct but less compact
  than a hand-written pattern.

## Capture Patterns

- Capture patterns are only detected from simple assignments that immediately
  read checked direct or nested sequence attributes, including attributes on
  matched sequence elements.
- Duplicate captures for the same source index are not converted.
- Capture extraction is conservative when body statements or index usage become
  ambiguous.
