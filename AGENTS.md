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

### Supported Pattern Types

1. **Literal Patterns** - Direct value comparisons
   - `if x == 1:` → `case 1:`
   - `if x == "hello":` → `case "hello":`
   - Supports: integers, floats, strings, negative numbers

2. **Identity Patterns** - Singleton comparisons
   - `if x is None:` → `case None:`
   - `if x is True:` → `case True:`
   - Only for None, True, False

3. **isinstance Patterns** - Type checking
   - `if isinstance(x, int):` → `case int():`
   - `if isinstance(x, (int, float)):` → `case int() | float():`

3a. **Nested isinstance Patterns** - isinstance checks on nested attributes
   - `if isinstance(x, NameExpr) and isinstance(x.node, Var):` → `case NameExpr(node=Var()):`
   - `if isinstance(x, Point) and isinstance(x.data, Data) and isinstance(x.data.value, List):` → `case Point(data=Data(value=List())):`
   - **With attribute checks on nested paths**: `if isinstance(x, NameExpr) and isinstance(x.node, Var) and x.node.type is None:` → `case NameExpr(node=Var(type=None)):`
   - Multiple attribute checks: `if isinstance(x, Point) and isinstance(x.data, Data) and x.data.x == 5 and x.data.y == 10:` → `case Point(data=Data(x=5, y=10)):`
   - **Tuple of classes on nested attributes**: `if isinstance(x, RefExpr) and isinstance(x.node, (Var, FuncDef)):` → `case RefExpr(node=Var() | FuncDef()):`
   - Supports unlimited nesting depth (recursive)
   - Attribute checks on nested paths are merged into the nested pattern structure
   - Only supports literal values or None/True/False for attribute checks

4. **Class Patterns with Attributes** - isinstance with attribute checks
   - `if isinstance(p, Point) and p.x == 5:` → `case Point(x=5):`
   - `if isinstance(p, Point) and p.x == 5 and p.y == 10:` → `case Point(x=5, y=10):`
   - Supports both `==` and `is` operators for attributes
   - **Sequence attributes**: `if isinstance(obj, Data) and len(obj.value) == 3 and obj.value[0] == 1 and obj.value[1] == 2 and obj.value[2] == 3:` → `case Data(value=[1, 2, 3]):`
   - Can mix scalar and sequence attributes: `case Container(items=[1, 2, 3], count=3):`
   - **Nested sequence attributes**: Fully supports recursive nesting like `Data(value=[Data(value=[1, 2, 3])])` - isinstance checks within sequence attributes are recursively processed with their own attributes

5. **Sequence Patterns** - Length and element checks
   - `if len(x) == 2 and x[0] == 0 and x[1] == 1:` → `case 0, 1:`
   - `if len(rgb) == 3 and rgb[0] == 255 and rgb[1] == 0 and rgb[2] == 0:` → `case 255, 0, 0:`
   - All indices must be checked (with literals, isinstance, or `is`) OR left as wildcards
   - Supports nested patterns: `if len(x) == 2 and isinstance(x[0], Point) and x[1] == 2:` → `case Point(), 2:`
   - Supports mixed element types: literals, isinstance checks, and identity (`is None`)
   - **Star patterns**: `if len(x) >= 2 and x[0] == 1 and x[1] == 2:` → `case 1, 2, *_:`
   - **Wildcard patterns**: `if len(x) == 3 and x[0] == 1 and x[2] == 3:` → `case 1, _, 3:`
     - Unchecked indices become `_` (wildcard) in the pattern
     - Maximum 2 consecutive wildcards allowed (3+ consecutive prevents conversion)
     - Can appear at start, middle, or end of sequence
     - Multiple wildcard groups allowed in same pattern (e.g., `case 1, _, 2, _, _, 5:`)
     - Works with all element types: literals, isinstance, `is None`

6. **Nested Sequence Patterns** - Sequences within sequences
   - `if len(x) == 2 and len(x[0]) == 2 and x[0][0] == 1 and x[0][1] == 2 and x[1] == 3:` → `case [1, 2], 3:`
   - `if len(z) == 2 and isinstance(z[0], Point) and len(z[1]) == 2 and z[1][0] == 1 and z[1][1] == 2:` → `case Point(), [1, 2]:`
   - Supports any nesting depth (recursive)
   - Can mix nested sequences with other pattern types
   - Each nested sequence must have its own `len()` check

7. **OR Patterns (|)** - Multiple values for same subject
   - `if x == 1 or x == 2:` → `case 1 | 2:`
   - `if color == "red" or color == "green" or color == "blue":` → `case "red" | "green" | "blue":`
   - `if x is None or x is False:` → `case None | False:`
   - All comparisons must be against the same subject
   - All values must be literals (integers, floats, strings, None, True, False)
   - Supports both `==` and `is` operators (but `is` only with singletons)
   - Can be mixed with other pattern types in a chain

8. **Guard Patterns (if clause)** - Additional conditions after pattern match
   - `if isinstance(x, Handler) and ENABLED:` → `case Handler() if ENABLED:`
   - `if isinstance(x, (Handler, Worker)) and PRODUCTION:` → `case Handler() | Worker() if PRODUCTION:`
   - `if isinstance(x, Config) and DEBUG and not VERBOSE:` → `case Config() if DEBUG and not VERBOSE:`
   - `if isinstance(tvar, ParamSpecType) and isinstance(mapped_arg, ParamSpecType):` → `case ParamSpecType() if isinstance(mapped_arg, ParamSpecType):`
   - Guard conditions must NOT reference the match subject (only independent variables/expressions)
   - Used for conditions that can't be expressed as pattern matching
   - Works with single classes or OR patterns of multiple classes
   - Can have isinstance checks on different variables as guards
   - Proper whitespace automatically added around `if` keyword

9. **Capture Patterns** - Extract values with variable binding
   - **Single capture**: `if isinstance(n, Point) and len(n.x) >= 1: value = n.x[0]` → `case Point(x=[value, *_]):`
   - **Multiple consecutive captures**: `if isinstance(n, Point) and len(n.x) >= 2: first = n.x[0]; second = n.x[1]` → `case Point(x=[first, second, *_]):`
   - **Non-consecutive indices**: `if isinstance(n, Point) and len(n.x) >= 4: first = n.x[0]; third = n.x[2]` → `case Point(x=[first, _, third, *_]):`
   - **Indices not starting from 0**: `if isinstance(n, Point) and len(n.x) >= 3: second = n.x[1]; third = n.x[2]` → `case Point(x=[_, second, third, *_]):`
   - **Multi-attribute captures**: `if isinstance(n, Point) and len(n.x) >= 1 and len(n.y) >= 1: x_val = n.x[0]; y_val = n.y[0]` → `case Point(x=[x_val, *_], y=[y_val, *_]):`
   - Second-pass transformation that detects assignments in case body
   - Removes redundant assignment statements
   - Automatically inserts wildcards for skipped or uncaptured indices
   - Can capture from multiple different attributes in the same pattern
   - Works with sequence attributes in class patterns

### Will Convert
✅ If/elif chains comparing the same variable/expression
✅ Chains with at least one `elif` (minimum 2 branches)
✅ Function call expressions (e.g., `if get_value() == 1`)
✅ Attribute access (e.g., `if obj.status == "ready"`)
✅ Chains with or without final `else`
✅ Mixed pattern types in same chain (e.g., isinstance + literals)
✅ Nested patterns: isinstance inside sequence patterns
✅ Mixed element types in sequences (literals, isinstance, `is None`)
✅ Nested sequences: sequences within sequences (e.g., `[[1, 2], 3]`)
✅ Recursive nesting: unlimited nesting depth for nested sequences
✅ Sequence attributes in class patterns (e.g., `Data(value=[1, 2, 3])`)
✅ Mixed scalar and sequence attributes (e.g., `Container(items=[1, 2], count=2)`)
✅ Nested isinstance with sequence attributes (e.g., `Data(value=[Data(value=[1, 2, 3])])`)
✅ Nested isinstance on nested attributes (e.g., `isinstance(x.node, Var)` → `case X(node=Var())`)
✅ Nested isinstance with attribute checks (e.g., `isinstance(x.node, Var) and x.node.type is None` → `case X(node=Var(type=None))`)
✅ Nested isinstance with tuple of classes (e.g., `isinstance(x.node, (Var, FuncDef))` → `case X(node=Var() | FuncDef())`)
✅ isinstance tuple inside sequences (e.g., `isinstance(x[0], (Point, Line))` → `case Point() | Line(), ...:` )
✅ Star patterns: `if len(x) >= 2 and x[0] == 1 and x[1] == 2:` → `case [1, 2, *_]:`
✅ Wildcard patterns: `if len(x) == 3 and x[0] == 1 and x[2] == 3:` → `case [1, _, 3]:`
✅ OR patterns: `if x == 1 or x == 2:` → `case 1 | 2:`
✅ Guard patterns: `if isinstance(x, Handler) and ENABLED:` → `case Handler() if ENABLED:`
✅ Capture patterns: Single or multiple assignment extraction with variable binding
✅ Multiple consecutive captures: Extract 2 or more values from sequence attributes
✅ Non-consecutive index captures: Automatically insert wildcards for skipped indices
✅ Multi-attribute captures: Extract values from different attributes in same pattern

### Will NOT Convert
❌ Single `if` without `elif`
❌ Chains comparing different variables/subjects
❌ Non-equality operators (`>`, `<`, `!=`, etc.) except `is`
❌ Sequence patterns with 3+ consecutive wildcards (e.g., `x[0] == 1 and x[4] == 5`)
❌ Sequence patterns without `len()` check
❌ isinstance tuple with attributes (e.g., `isinstance(x, (Point, Line)) and x.value == 5`)
❌ Non-literal values in patterns (variables would create binding patterns)
❌ OR patterns with different subjects (e.g., `if x == 1 or y == 2:`)
❌ OR patterns with non-literal values (e.g., `if x == 1 or x == variable:`)
❌ Guard patterns that reference the subject (e.g., `isinstance(x, Class) and x.attr == value` should be class pattern)
❌ Capture patterns with duplicate indices (e.g., `n.x[0]` twice)

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
