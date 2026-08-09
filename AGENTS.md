# Agent Instructions for Matchify

Matchify converts eligible `if`/`elif`/`else` chains into Python 3.10+
`match` statements. It uses LibCST so transformations preserve source formatting.

## Code map

- `src/matchify/transform.py` orchestrates the LibCST transformation and exposes
  `transform_code()`.
- `src/matchify/compiler.py` normalizes complete chains and compiles them into
  `match` statements.
- `src/matchify/conditions.py` parses conditions into typed predicates.
- `src/matchify/access_path.py` models subjects and nested attribute/index paths.
- `src/matchify/pattern_builder.py` lowers predicates into pattern facts and
  residual guards.
- `src/matchify/facts.py` and `src/matchify/patterns.py` define and render the
  pattern IR.
- `src/matchify/safety.py` checks whether transformations preserve behavior.
- `src/matchify/capture_patterns.py` turns eligible assignments into capture
  patterns.
- `src/matchify/cli.py` implements file processing and the CLI;
  `src/matchify/__main__.py` is the `python -m matchify` entry point.

## Transformation principles

- Preserve runtime semantics. Be conservative when evaluation count/order,
  side effects, bindings, or pattern behavior are uncertain.
- Convert only complete chains with at least one `elif`; leave unsupported
  conditions unchanged.
- Conditions in a converted chain must resolve to a compatible match subject.
- Literal, singleton identity, class, sequence, OR, guard, nested, and capture
  patterns are supported where the builder and safety checks can prove them
  valid. Treat the behavior-focused tests as the authoritative specification.
- Non-literal expressions must not accidentally become capture patterns.
- A walrus expression that must execute as part of a condition belongs in a
  guard, not in the match subject or structural pattern.

## LibCST notes

- For `elif`, `cst.If.orelse` is another `cst.If`; for `else`, it is a
  `cst.Else` whose `body` contains the suite.
- Use `.deep_equals()` for structural CST comparisons.
- Build a wildcard case with `cst.MatchAs(pattern=None, name=None)`.
- Pass concrete pattern nodes such as `cst.MatchValue` directly to
  `cst.MatchCase.pattern`; `cst.MatchPattern` is abstract.

## Development workflow

1. Add a minimal behavior-focused regression test before or alongside a fix.
2. Make changes in the appropriate parsing, lowering, rendering, or safety
   layer rather than adding syntax-specific exceptions to orchestration code.
3. Exercise transformations through `transform_code()`, `convert_file()`, or
   the CLI when practical.
4. Run the focused test, then the full suite:

   ```bash
   uv run pytest tests/test_transform.py -k <case>
   uv run pytest
   ```

The test suite is organized as follows:

- `tests/test_transform.py` and `tests/test_edge_cases.py`: source-to-source
  behavior and rejection cases.
- `tests/test_cli.py`: file processing and CLI behavior.
- `tests/test_code_samples.py`: executable source samples whose runtime traces
  are compared before and after transformation.

Use `textwrap.dedent()` for multiline source fixtures and temporary directories
for filesystem tests. Test both successful conversions and nearby cases that
must remain unchanged.

For a complex generated-roundtrip failure, `pysource-minimize` can reduce a
reproducer. Use a precise checker that transforms the program and detects the
specific trace mismatch; broad checks can minimize to an unrelated failure.
