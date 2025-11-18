# Agent Instructions for Matchify

This document provides guidance for AI coding agents working with the Matchify codebase.

## Project Overview

Matchify is a Python tool that automatically converts if/elif/else chains into Python 3.10+ match statements. It uses LibCST for parsing and transforming Python code while preserving formatting and structure.

## Architecture

### Core Components

1. **`src/matchify/__main__.py`** - Main module containing:
   - `IfToMatchTransformer` - LibCST transformer that converts if-chains to match statements
   - `convert_file()` - File processing function
   - `main()` - CLI entry point

2. **`tests/test_cli.py`** - Comprehensive test suite covering:
   - Transformer logic
   - File operations
   - CLI functionality
   - Edge cases

### Key Classes and Methods

#### `IfToMatchTransformer`
- Extends `cst.CSTTransformer`
- Uses `PositionProvider` metadata
- Key methods:
  - `_extract_subject()` - Extracts left side of `==` comparisons
  - `_is_simple_equality_chain()` - Validates if-chain is convertible
  - `leave_If()` - Main transformation logic

## LibCST API Usage

### Important Nodes
- `cst.Match` - Match statement (takes `subject` and `cases`)
- `cst.MatchCase` - Individual case (takes `pattern` and `body`)
- `cst.MatchValue` - Pattern for literal values
- `cst.MatchAs(pattern=None, name=None)` - Wildcard pattern for `case _:`

### Common Patterns
```python
# Creating a match statement
match_stmt = cst.Match(
    subject=expression,
    cases=[
        cst.MatchCase(
            pattern=cst.MatchValue(value=literal),
            body=indented_block,
        ),
        # Wildcard case
        cst.MatchCase(
            pattern=cst.MatchAs(pattern=None, name=None),
            body=indented_block,
        ),
    ]
)
```

### Navigation
- `if_node.orelse` - For if/elif: another `cst.If` node directly (not wrapped)
- `if_node.orelse` - For if/else: a `cst.Else` node with `.body` attribute
- Use `.deep_equals()` for structural comparison (not `==` or `is`)

## Conversion Rules

### Will Convert
✅ If/elif chains comparing the same variable/expression with `==`
✅ Chains with at least one `elif` (minimum 2 branches)
✅ Function call expressions (e.g., `if get_value() == 1`)
✅ Attribute access (e.g., `if obj.status == "ready"`)
✅ Chains with or without final `else`

### Will NOT Convert
❌ Single `if` without `elif`
❌ Chains comparing different variables
❌ Non-equality operators (`>`, `<`, `!=`, etc.)
❌ Mixed operators in the chain

## Testing Guidelines

### Running Tests
```bash
uv run pytest              # Run all tests
uv run pytest -v           # Verbose output
uv run pytest -xvs         # Stop on first failure with output
```

### Test Structure
Tests are organized into classes:
- `TestIfToMatchTransformer` - Core transformation logic
- `TestConvertFile` - File operations
- `TestMain` - CLI behavior
- `TestExtractSubject` - Helper method validation

### Writing New Tests
- Use `textwrap.dedent()` for multiline code strings
- Use `tempfile.TemporaryDirectory()` for file operations
- Use `cst.parse_module()` and `cst.MetadataWrapper()` for transformation tests
- Test both positive cases (should convert) and negative cases (should not convert)

## Common Tasks

### Adding a New Pattern Type
1. Update `_extract_subject()` to recognize the pattern
2. Add validation in `_is_simple_equality_chain()`
3. Handle in `leave_If()` transformation logic
4. Add test cases in `test_cli.py`

### Fixing Transformation Bugs
1. Create a minimal test case that demonstrates the bug
2. Use `cst.parse_module()` to inspect the AST structure
3. Check node navigation (`orelse`, `body`, etc.)
4. Verify with `node.deep_equals()` for structural comparison
5. Run full test suite to ensure no regressions

### Debugging LibCST Issues
```python
# Print the full CST structure
import libcst as cst
tree = cst.parse_module(code)
print(tree)

# Check node types
print(type(node))
print(isinstance(node, cst.If))

# Use deep_equals for comparison
node1.deep_equals(node2)
```

## Dependencies

- **libcst>=1.8.6** - Core CST parsing and transformation
- **pytest** - Testing framework
- **inline-snapshot** - Snapshot testing support

## Development Workflow

1. Make changes to source code
2. Add/update tests in `test_cli.py`
3. Run tests: `uv run pytest`
4. Fix any issues revealed by tests
5. Ensure all tests pass before committing

## Common Pitfalls

1. **Don't use object identity** - Use `.deep_equals()` not `==` or `is`
2. **Don't wrap patterns** - Pass `MatchValue` directly to `MatchCase.pattern`, not wrapped in `MatchPattern`
3. **Navigation confusion** - `elif` is `orelse: If`, not `orelse.body: If`
4. **Wildcard pattern** - Use `MatchAs(pattern=None, name=None)`, not `MatchAs(name=Name("_"))`
5. **Abstract classes** - Some CST nodes like `MatchPattern` are abstract; use concrete implementations

## Resources

- [LibCST Documentation](https://libcst.readthedocs.io/)
- [Python match statement PEP](https://peps.python.org/pep-0636/)
- Project repository: https://github.com/15r10nk/matchify
