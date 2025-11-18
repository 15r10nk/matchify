# if_to_match_converter.py
#
# A standalone script that converts simple if/elif/else chains
# that compare the same variable with == into a Python 3.10+ match statement.
#
# Usage:
#   python if_to_match_converter.py path/to/your_file.py
#   python if_to_match_converter.py path/to/project/**/*.py   # with glob
#
# It reads the file, transforms eligible if-chains and writes the result back.

import argparse
import multiprocessing
import pathlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List

import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider


class IfToMatchTransformer(cst.CSTTransformer):
    """
    Converts chains of the form:
        if x == 1: ...
        elif x == 2: ...
        else: ...
    into:
        match x:
            case 1: ...
            case 2: ...
            case _: ...
    Only chains that compare the *same* left-hand expression are transformed.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self) -> None:
        super().__init__()
        # Will be set when we enter the first If of a chain
        self._current_subject: cst.BaseExpression | None = None
        # Track which If nodes are elif clauses (in orelse position)
        self._elif_nodes: set[int] = set()

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #
    def _extract_subject(self, test: cst.BaseExpression) -> cst.BaseExpression | None:
        """Return the left side of a simple == or 'is' comparison or isinstance call, otherwise None."""
        # Check for equality or identity comparison
        if m.matches(
            test,
            m.Comparison(
                comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())],
            ),
        ):
            comp = test  # type: ignore
            return comp.left
        
        # Check for isinstance(subject, type)
        if m.matches(
            test,
            m.Call(
                func=m.Name(value="isinstance"),
                args=[m.Arg(), m.Arg()],
            ),
        ):
            call = test  # type: ignore
            return call.args[0].value
        
        # Check for isinstance(subject, type) and subject.attr == value
        # The isinstance could be nested in the left side
        if m.matches(test, m.BooleanOperation(operator=m.And())):
            def find_isinstance_subject(node: cst.BaseExpression) -> cst.BaseExpression | None:
                if self._is_isinstance_call(node):
                    call = node  # type: ignore
                    return call.args[0].value
                if m.matches(node, m.BooleanOperation(operator=m.And())):
                    bool_op = node  # type: ignore
                    return find_isinstance_subject(bool_op.left)
                return None
            
            result = find_isinstance_subject(test)
            if result is not None:
                return result
        
        return None

    def _is_literal_value(self, node: cst.BaseExpression) -> bool:
        """Check if a node is a literal value (not a variable/name).
        
        Only literal values can be safely used in match case patterns.
        Names would become binding patterns, which changes semantics.
        """
        # Check for unary minus/plus on numbers (e.g., -5, +3.14)
        if m.matches(node, m.UnaryOperation(operator=m.Minus() | m.Plus())):
            unary = node  # type: ignore
            return m.matches(unary.expression, m.Integer() | m.Float())
        
        return m.matches(
            node,
            m.Integer()
            | m.Float()
            | m.SimpleString()
            | m.ConcatenatedString()
            | m.FormattedString()
            | m.Name(value="True")
            | m.Name(value="False")
            | m.Name(value="None")
        )

    def _is_isinstance_call(self, test: cst.BaseExpression) -> bool:
        """Check if test is an isinstance(subject, type) call."""
        return m.matches(
            test,
            m.Call(
                func=m.Name(value="isinstance"),
                args=[m.Arg(), m.Arg()],
            ),
        )
    
    def _is_isinstance_with_and(self, test: cst.BaseExpression) -> bool:
        """Check if test is isinstance(subject, type) and subject.attr == value."""
        if not m.matches(test, m.BooleanOperation(operator=m.And())):
            return False
        
        # Need to find isinstance somewhere in the left side (could be nested)
        def has_isinstance(node: cst.BaseExpression) -> bool:
            if self._is_isinstance_call(node):
                return True
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                return has_isinstance(bool_op.left)
            return False
        
        bool_op = test  # type: ignore
        return has_isinstance(bool_op.left)
    
    def _extract_isinstance_classes(self, test: cst.BaseExpression) -> list[cst.BaseExpression] | None:
        """Extract the class(es) from isinstance(subject, Class) or isinstance(subject, (Class1, Class2)) call.
        
        Returns a list of class expressions, or None if not a valid isinstance call.
        """
        if self._is_isinstance_call(test):
            call = test  # type: ignore
            class_arg = call.args[1].value
            
            # Check if it's a tuple of classes
            if isinstance(class_arg, cst.Tuple):
                classes = []
                for element in class_arg.elements:
                    if isinstance(element, cst.Element):
                        classes.append(element.value)
                    elif isinstance(element, cst.StarredElement):
                        # Don't support *args in isinstance tuples
                        return None
                return classes if classes else None
            else:
                # Single class
                return [class_arg]
        return None
    
    def _extract_isinstance_with_attrs(self, test: cst.BaseExpression) -> tuple[cst.BaseExpression, list[tuple[str, cst.BaseExpression]]] | None:
        """Extract class and attribute checks from isinstance(subject, Class) and subject.attr == value.
        
        Returns (class_expr, [(attr_name, value), ...]) or None if not a valid pattern.
        """
        if not self._is_isinstance_with_and(test):
            return None
        
        # Find the isinstance call (could be nested in left side of BooleanOperations)
        def find_isinstance(node: cst.BaseExpression) -> cst.Call | None:
            if self._is_isinstance_call(node):
                return node  # type: ignore
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                return find_isinstance(bool_op.left)
            return None
        
        isinstance_call = find_isinstance(test)
        if isinstance_call is None:
            return None
            
        subject = isinstance_call.args[0].value
        class_arg = isinstance_call.args[1].value
        
        # Don't support tuple of classes with attributes yet
        if isinstance(class_arg, cst.Tuple):
            return None
        
        # Extract attribute checks from the entire test expression
        attrs = []
        
        # Handle single comparison or chain of and comparisons
        def extract_attr_checks(node: cst.BaseExpression) -> bool:
            """Recursively extract attribute checks. Returns False if invalid pattern."""
            # Skip isinstance calls
            if self._is_isinstance_call(node):
                return True
            
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                and_op = node  # type: ignore
                return extract_attr_checks(and_op.left) and extract_attr_checks(and_op.right)
            elif m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())])):
                comp = node  # type: ignore
                # Check if left side is subject.attr
                if m.matches(comp.left, m.Attribute()):
                    attr = comp.left  # type: ignore
                    # Verify the attribute is on the same subject
                    if attr.value.deep_equals(subject):
                        attr_name = attr.attr.value
                        value = comp.comparisons[0].comparator
                        operator = comp.comparisons[0].operator
                        
                        # 'is' operator should only be used with singletons
                        if isinstance(operator, cst.Is):
                            if not m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                                return False
                        # Only support literal values for '=='
                        elif not self._is_literal_value(value):
                            return False
                        
                        attrs.append((attr_name, value))
                        return True
            return False
        
        if extract_attr_checks(test):
            return (class_arg, attrs)
        return None

    def _is_simple_equality_chain(self, node: cst.If) -> bool:
        """Very cheap heuristic – we only convert obvious == chains or isinstance chains.
        
        Supports:
        - Pure equality chains with literals: if x == 1: ... elif x == 2: ...
        - Pure isinstance chains: if isinstance(x, int): ... elif isinstance(x, str): ...
        - Mixed chains: if x is None: ... elif isinstance(x, Color): ...
        """
        current: cst.If | cst.BaseStatement = node
        subject = self._extract_subject(current.test)
        if subject is None:
            return False

        # Must have at least one elif to form a chain
        if current.orelse is None or not isinstance(current.orelse, cst.If):
            # Single if without elif - don't convert
            return False

        has_elif = False
        while True:
            if isinstance(current, cst.If):
                current_subject = self._extract_subject(current.test)
                if current_subject is None or not current_subject.deep_equals(subject):
                    return False
                
                # Each branch must be either isinstance, isinstance with and, or equality with literal
                if self._is_isinstance_call(current.test) or self._is_isinstance_with_and(current.test):
                    # isinstance is always valid
                    pass
                else:
                    # For equality/identity chains, check that we're comparing against a literal value
                    comparison = current.test  # type: ignore
                    comparator = comparison.comparisons[0].comparator
                    operator = comparison.comparisons[0].operator
                    
                    # 'is' operator should only be used with singletons (None, True, False)
                    if isinstance(operator, cst.Is):
                        if not m.matches(comparator, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                            return False
                    elif not self._is_literal_value(comparator):
                        return False
                
                orelse = current.orelse
                if orelse is None:
                    break
                if isinstance(orelse, cst.If):
                    has_elif = True
                    current = orelse
                    continue
                if isinstance(orelse, cst.Else):
                    break
            break
        return has_elif

    # ------------------------------------------------------------------ #
    # Visitor implementation
    # ------------------------------------------------------------------ #
    def visit_If(self, node: cst.If) -> bool:
        """Mark all elif nodes before transformation."""
        # If this If has an orelse that's also an If, mark it as an elif
        if isinstance(node.orelse, cst.If):
            self._elif_nodes.add(id(node.orelse))
        return True

    def leave_If(
        self, original_node: cst.If, updated_node: cst.If
    ) -> cst.BaseStatement | cst.FlattenSentinel[cst.BaseStatement] | cst.RemovalSentinel:
        # We only care about the *first* If of a chain
        if self._current_subject is not None:
            # Already inside a chain that is being replaced → let the root handle it
            return updated_node

        # Don't convert elif nodes - only convert complete chains starting with 'if'
        if id(original_node) in self._elif_nodes:
            return updated_node

        if not self._is_simple_equality_chain(original_node):
            return updated_node

        # ------------------------------------------------------------------
        # Collect the whole chain
        # ------------------------------------------------------------------
        cases: List[cst.MatchCase] = []
        current: cst.If | None = original_node

        while current is not None:
            subject = self._extract_subject(current.test)
            if subject is None:
                # Should never happen because of the earlier check
                return updated_node

            # First node in the chain → remember the subject
            if self._current_subject is None:
                self._current_subject = subject

            # Build the case for the current if/elif
            if self._is_isinstance_with_and(current.test):
                # isinstance(subject, Class) and subject.attr == value -> case Class(attr=value):
                result = self._extract_isinstance_with_attrs(current.test)
                if result is None:
                    return updated_node
                class_expr, attrs = result
                
                # Build keyword arguments for the class pattern
                kwds = []
                for attr_name, value in attrs:
                    # Create MatchKeywordElement for each attribute
                    if m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                        pattern = cst.MatchSingleton(value=value)
                    else:
                        pattern = cst.MatchValue(value=value)
                    
                    kwds.append(cst.MatchKeywordElement(
                        key=cst.Name(attr_name),
                        pattern=pattern
                    ))
                
                case_pattern = cst.MatchClass(cls=class_expr, patterns=[], kwds=kwds)
            elif self._is_isinstance_call(current.test):
                # isinstance(subject, Class) -> case Class():
                # isinstance(subject, (Class1, Class2)) -> case Class1() | Class2():
                class_exprs = self._extract_isinstance_classes(current.test)
                if class_exprs is None:
                    return updated_node
                
                if len(class_exprs) == 1:
                    # Single class: case Class():
                    case_pattern = cst.MatchClass(cls=class_exprs[0], patterns=[])
                else:
                    # Multiple classes: case Class1() | Class2() | ...
                    # Need to wrap in MatchOrElement with proper separators
                    or_elements = []
                    for i, cls in enumerate(class_exprs):
                        match_class = cst.MatchClass(cls=cls, patterns=[])
                        # All but the last element need a BitOr separator
                        if i < len(class_exprs) - 1:
                            or_elements.append(cst.MatchOrElement(
                                pattern=match_class,
                                separator=cst.BitOr()
                            ))
                        else:
                            or_elements.append(cst.MatchOrElement(pattern=match_class))
                    case_pattern = cst.MatchOr(patterns=or_elements)
            else:
                # subject == value -> case value:
                comparator = current.test.comparisons[0].comparator  # type: ignore
                # Use MatchSingleton for None, True, False
                if m.matches(comparator, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                    case_pattern = cst.MatchSingleton(value=comparator)
                else:
                    case_pattern = cst.MatchValue(value=comparator)
            
            cases.append(
                cst.MatchCase(
                    pattern=case_pattern,
                    body=current.body,
                )
            )

            # Move to the next part of the chain
            orelse = current.orelse
            if isinstance(orelse, cst.Else):
                # Final else → use MatchAs with pattern=None and name=None for wildcard
                wildcard_pattern = cst.MatchAs(pattern=None, name=None)
                cases.append(
                    cst.MatchCase(
                        pattern=wildcard_pattern,
                        body=orelse.body,
                    )
                )
                break
            elif isinstance(orelse, cst.If):
                current = orelse
                continue
            else:
                # No else clause at the end
                break

        # ------------------------------------------------------------------
        # Build the final match statement
        # ------------------------------------------------------------------
        match_stmt = cst.Match(
            subject=self._current_subject,
            cases=cases,
        )

        # Reset for the next top-level If
        self._current_subject = None

        return match_stmt


def convert_file(path: pathlib.Path) -> tuple[pathlib.Path, bool, str | None]:
    """Convert a single file.
    
    Returns:
        Tuple of (path, changed, error_message)
    """
    try:
        source = path.read_text(encoding="utf-8")
        module = cst.parse_module(source)

        wrapper = cst.MetadataWrapper(module)
        transformed = wrapper.visit(IfToMatchTransformer())

        # Only write back if something changed
        if transformed.code != source:
            path.write_text(transformed.code, encoding="utf-8")
            return (path, True, None)
        else:
            return (path, False, None)
    except Exception as e:
        return (path, False, str(e))


def collect_python_files(paths: List[pathlib.Path]) -> List[pathlib.Path]:
    """Collect all Python files from the given paths."""
    python_files = []
    for arg in paths:
        if arg.is_file() and arg.suffix == ".py":
            python_files.append(arg)
        elif arg.is_dir():
            python_files.extend(arg.rglob("*.py"))
        else:
            print(f"Skipping (not a Python file): {arg}")
    return python_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert if/elif/else chains to Python 3.10+ match statements"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=pathlib.Path,
        help="Python files or directories to process"
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=None,
        help="Number of parallel jobs (default: number of CPU cores)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show files with no changes"
    )
    
    args = parser.parse_args()
    
    # Collect all Python files
    python_files = collect_python_files(args.paths)
    
    if not python_files:
        print("No Python files found to process")
        return
    
    # Determine number of workers
    max_workers = args.jobs or multiprocessing.cpu_count()
    
    # Process files in parallel
    converted_count = 0
    unchanged_count = 0
    error_count = 0
    
    if len(python_files) == 1:
        # Single file - no need for multiprocessing
        path, changed, error = convert_file(python_files[0])
        if error:
            print(f"Error processing {path}: {error}")
            error_count += 1
        elif changed:
            print(f"Converted: {path}")
            converted_count += 1
        elif args.verbose:
            print(f"No changes: {path}")
            unchanged_count += 1
        else:
            unchanged_count += 1
    else:
        # Multiple files - use parallel processing
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_path = {executor.submit(convert_file, path): path for path in python_files}
            
            # Process results as they complete
            for future in as_completed(future_to_path):
                path, changed, error = future.result()
                if error:
                    print(f"Error processing {path}: {error}")
                    error_count += 1
                elif changed:
                    print(f"Converted: {path}")
                    converted_count += 1
                elif args.verbose:
                    print(f"No changes: {path}")
                    unchanged_count += 1
                else:
                    unchanged_count += 1
    
    # Print summary
    print(f"\nSummary: {converted_count} converted, {unchanged_count} unchanged, {error_count} errors")


if __name__ == "__main__":
    main()