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
        
        # Check for sequence pattern: len(x) == N and x[0] == val0 ...
        if self._is_sequence_pattern(test):
            result = self._extract_sequence_pattern(test)
            if result is not None:
                return result[0]
        
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
    
    def _build_nested_sequence_pattern(self, patterns: list) -> cst.MatchList:
        """Recursively build a nested sequence pattern from pattern metadata.
        
        Args:
            patterns: List of (pattern_type, pattern_data) tuples
            
        Returns:
            A MatchList node containing the nested patterns
        """
        elements = []
        for j, (pattern_type, pattern_data) in enumerate(patterns):
            if pattern_type == 'literal':
                value = pattern_data
                if m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                    pattern = cst.MatchSingleton(value=value)
                else:
                    pattern = cst.MatchValue(value=value)
            elif pattern_type == 'isinstance':
                classes = pattern_data
                if len(classes) == 1:
                    pattern = cst.MatchClass(cls=classes[0], patterns=[])
                else:
                    class_patterns = [cst.MatchClass(cls=cls, patterns=[]) for cls in classes]
                    pattern = cst.MatchOr(patterns=class_patterns)
            elif pattern_type == 'sequence':
                # Recursive call for deeper nesting
                pattern = self._build_nested_sequence_pattern(pattern_data)
            else:
                raise ValueError(f"Unknown pattern type: {pattern_type}")
            
            if j < len(patterns) - 1:
                elements.append(cst.MatchSequenceElement(
                    value=pattern,
                    comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                ))
            else:
                elements.append(cst.MatchSequenceElement(value=pattern))
        
        # Return MatchList WITH brackets for nested sequences
        return cst.MatchList(
            patterns=elements,
            lbracket=cst.LeftSquareBracket(),
            rbracket=cst.RightSquareBracket(),
        )
    
    def _extract_isinstance_with_attrs(self, test: cst.BaseExpression) -> tuple[cst.BaseExpression, list[tuple[str, cst.BaseExpression | tuple[str, list]]]] | None:
        """Extract class and attribute checks from isinstance(subject, Class) and subject.attr == value.
        
        Returns (class_expr, [(attr_name, value), ...]) or None if not a valid pattern.
        
        The value can be:
        - A CST expression for simple values: (attr_name, value_expr)
        - A tuple for sequence patterns: (attr_name, ('sequence', pattern_list))
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
        
        # First, identify which attributes have sequence patterns
        # Look for len(subject.attr) == N patterns
        sequence_attrs: dict[str, bool] = {}
        
        def find_sequence_attrs(node: cst.BaseExpression) -> None:
            """Find attributes that are checked as sequences."""
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                # Check for len(subject.attr) == N
                if m.matches(comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
                    call = comp.left  # type: ignore
                    if len(call.args) > 0:
                        len_arg = call.args[0].value
                        if m.matches(len_arg, m.Attribute()):
                            attr_expr = len_arg  # type: ignore
                            if attr_expr.value.deep_equals(subject):
                                attr_name = attr_expr.attr.value
                                sequence_attrs[attr_name] = True
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                and_op = node  # type: ignore
                find_sequence_attrs(and_op.left)
                find_sequence_attrs(and_op.right)
        
        find_sequence_attrs(test)
        
        # Extract attribute checks from the entire test expression
        attrs = []
        
        # For each sequence attribute, extract its pattern
        for attr_name in sequence_attrs:
            # Collect all conditions related to this attribute
            attr_conditions = []
            
            def collect_attr_conditions(node: cst.BaseExpression) -> None:
                """Collect conditions related to subject.attr sequence."""
                if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())])):
                    comp = node  # type: ignore
                    # Check for len(subject.attr) == N
                    if m.matches(comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
                        call = comp.left  # type: ignore
                        if len(call.args) > 0:
                            len_arg = call.args[0].value
                            if m.matches(len_arg, m.Attribute()):
                                attr_expr = len_arg  # type: ignore
                                if attr_expr.value.deep_equals(subject) and attr_expr.attr.value == attr_name:
                                    attr_conditions.append(node)
                                    return
                    # Check for subject.attr[i] == value or isinstance(subject.attr[i], Class)
                    if m.matches(comp.left, m.Subscript()):
                        subscript = comp.left  # type: ignore
                        if m.matches(subscript.value, m.Attribute()):
                            attr_expr = subscript.value  # type: ignore
                            if attr_expr.value.deep_equals(subject) and attr_expr.attr.value == attr_name:
                                attr_conditions.append(node)
                                return
                elif m.matches(node, m.Call(func=m.Name(value="isinstance"))):
                    call = node  # type: ignore
                    if len(call.args) >= 1:
                        isinstance_arg = call.args[0].value
                        # Check for isinstance(subject.attr[i], Class)
                        if m.matches(isinstance_arg, m.Subscript()):
                            subscript = isinstance_arg  # type: ignore
                            if m.matches(subscript.value, m.Attribute()):
                                attr_expr = subscript.value  # type: ignore
                                if attr_expr.value.deep_equals(subject) and attr_expr.attr.value == attr_name:
                                    attr_conditions.append(node)
                                    return
                elif m.matches(node, m.BooleanOperation(operator=m.And())):
                    and_op = node  # type: ignore
                    collect_attr_conditions(and_op.left)
                    collect_attr_conditions(and_op.right)
            
            collect_attr_conditions(test)
            
            if attr_conditions:
                # Build a test expression from these conditions
                attr_test = attr_conditions[0]
                for cond in attr_conditions[1:]:
                    attr_test = cst.BooleanOperation(
                        left=attr_test,
                        operator=cst.And(),
                        right=cond
                    )
                
                # Extract as a sequence pattern, but the subject is subject.attr
                # We need to build the equivalent check for subject.attr
                result = self._extract_sequence_pattern(attr_test)
                if result:
                    _, patterns = result
                    attrs.append((attr_name, ('sequence', patterns)))
                else:
                    return None
        
        # Handle single comparison or chain of and comparisons for scalar attributes
        def extract_attr_checks(node: cst.BaseExpression) -> bool:
            """Recursively extract attribute checks. Returns False if invalid pattern."""
            # Skip isinstance calls
            if self._is_isinstance_call(node):
                return True
            
            # Skip len() calls - these are handled by sequence attribute extraction
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"))):
                    return True
            
            # Skip checks on subscripted attributes (subject.attr[i])
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Subscript()):
                    subscript = comp.left  # type: ignore
                    if m.matches(subscript.value, m.Attribute()):
                        return True
            
            # Skip isinstance checks on subscripted attributes
            if m.matches(node, m.Call(func=m.Name(value="isinstance"))):
                call = node  # type: ignore
                if len(call.args) >= 1 and m.matches(call.args[0].value, m.Subscript()):
                    subscript = call.args[0].value  # type: ignore
                    if m.matches(subscript.value, m.Attribute()):
                        return True
            
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                and_op = node  # type: ignore
                return extract_attr_checks(and_op.left) and extract_attr_checks(and_op.right)
            elif m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())])):
                comp = node  # type: ignore
                # Check if left side is subject.attr (not subscripted)
                if m.matches(comp.left, m.Attribute()):
                    attr = comp.left  # type: ignore
                    # Verify the attribute is on the same subject
                    if attr.value.deep_equals(subject):
                        attr_name = attr.attr.value
                        # Skip if this is a sequence attribute
                        if attr_name in sequence_attrs:
                            return True
                        
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

    def _is_sequence_pattern(self, test: cst.BaseExpression) -> bool:
        """Check if test matches: len(x) == N and x[0] == val0 and x[1] == val1 ..."""
        if not m.matches(test, m.BooleanOperation(operator=m.And())):
            return False
        
        # Need to find len(subject) == N check
        def has_len_check(node: cst.BaseExpression) -> bool:
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                # Check for len(x) == N
                if m.matches(comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
                    comparator = comp.comparisons[0].comparator
                    return m.matches(comparator, m.Integer())
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                return has_len_check(bool_op.left) or has_len_check(bool_op.right)
            return False
        
        return has_len_check(test)
    
    def _extract_sequence_pattern(self, test: cst.BaseExpression) -> tuple[cst.BaseExpression, list[tuple[str, cst.BaseExpression | list[cst.BaseExpression]]]] | None:
        """Extract subject and pattern info from sequence patterns.
        
        Handles patterns like:
        - len(x) == N and x[0] == val0 and x[1] == val1 -> (x, [('literal', val0), ('literal', val1)])
        - len(x) == N and isinstance(x[0], Class) and x[1] == val -> (x, [('isinstance', Class), ('literal', val)])
        
        Returns (subject, [(pattern_type, pattern_value), ...]) or None if not valid.
        """
        if not self._is_sequence_pattern(test):
            return None
        
        # Find len(subject) == N
        subject = None
        expected_len = None
        
        def find_len_check(node: cst.BaseExpression) -> None:
            nonlocal subject, expected_len
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
                    call = comp.left  # type: ignore
                    subject = call.args[0].value
                    comparator = comp.comparisons[0].comparator
                    if m.matches(comparator, m.Integer()):
                        expected_len = int(comparator.value)  # type: ignore
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                find_len_check(bool_op.left)
                if subject is None:
                    find_len_check(bool_op.right)
        
        find_len_check(test)
        if subject is None or expected_len is None:
            return None
        
        expected_len_val = expected_len  # For type checking in closure
        
        # Now collect pattern info for each index: x[i] == value or isinstance(x[i], Class)
        patterns: list[tuple[str, cst.BaseExpression | list[cst.BaseExpression]] | None] = [None] * expected_len_val
        
        # Track which indices might be nested sequences
        nested_sequence_indices = set()
        
        # First pass: identify indices that might be nested sequences (have len() checks)
        def find_nested_sequences(node: cst.BaseExpression) -> None:
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
                    call = comp.left  # type: ignore
                    len_arg = call.args[0].value
                    if m.matches(len_arg, m.Subscript()):
                        subscript = len_arg  # type: ignore
                        if subscript.value.deep_equals(subject):
                            if len(subscript.slice) == 1:
                                slice_elem = subscript.slice[0]
                                if isinstance(slice_elem.slice, cst.Index):
                                    index_val = slice_elem.slice.value
                                    if m.matches(index_val, m.Integer()):
                                        idx = int(index_val.value)  # type: ignore
                                        if 0 <= idx < expected_len_val:
                                            nested_sequence_indices.add(idx)
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                find_nested_sequences(bool_op.left)
                find_nested_sequences(bool_op.right)
        
        find_nested_sequences(test)
        
        # For nested sequences, we need to recursively extract them
        for idx in nested_sequence_indices:
            
            # Collect conditions about x[idx] into a list
            nested_conditions = []
            
            def collect_nested_conditions(node: cst.BaseExpression) -> None:
                # Check if this node involves x[idx]
                if m.matches(node, m.Comparison()):
                    comp = node  # type: ignore
                    # Check if left side is len(x[idx])
                    if m.matches(comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])):
                        call = comp.left  # type: ignore
                        if len(call.args) > 0:
                            len_arg = call.args[0].value
                            if isinstance(len_arg, cst.Subscript) and len_arg.value.deep_equals(subject):
                                if len(len_arg.slice) == 1:
                                    slice_elem = len_arg.slice[0]
                                    if isinstance(slice_elem.slice, cst.Index):
                                        if m.matches(slice_elem.slice.value, m.Integer()):
                                            check_idx = int(slice_elem.slice.value.value)  # type: ignore
                                            if check_idx == idx:
                                                nested_conditions.append(node)
                                                return
                    # Check if left side is x[idx][...]
                    if m.matches(comp.left, m.Subscript()):
                        subscript = comp.left  # type: ignore
                        if isinstance(subscript.value, cst.Subscript) and subscript.value.value.deep_equals(subject):
                            if len(subscript.value.slice) == 1:
                                slice_elem = subscript.value.slice[0]
                                if isinstance(slice_elem.slice, cst.Index):
                                    if m.matches(slice_elem.slice.value, m.Integer()):
                                        check_idx = int(slice_elem.slice.value.value)  # type: ignore
                                        if check_idx == idx:
                                            nested_conditions.append(node)
                                            return
                elif m.matches(node, m.Call(func=m.Name(value="isinstance"))):
                    call = node  # type: ignore
                    if len(call.args) >= 1:
                        isinstance_arg = call.args[0].value
                        if isinstance(isinstance_arg, cst.Subscript):
                            # Check for isinstance(x[idx][...], ...)
                            if isinstance(isinstance_arg.value, cst.Subscript) and isinstance_arg.value.value.deep_equals(subject):
                                if len(isinstance_arg.value.slice) == 1:
                                    slice_elem = isinstance_arg.value.slice[0]
                                    if isinstance(slice_elem.slice, cst.Index):
                                        if m.matches(slice_elem.slice.value, m.Integer()):
                                            check_idx = int(slice_elem.slice.value.value)  # type: ignore
                                            if check_idx == idx:
                                                nested_conditions.append(node)
                                                return
                elif m.matches(node, m.BooleanOperation(operator=m.And())):
                    bool_op = node  # type: ignore
                    collect_nested_conditions(bool_op.left)
                    collect_nested_conditions(bool_op.right)
            
            collect_nested_conditions(test)
            
            if nested_conditions:
                # Build a combined AND expression from the nested conditions
                nested_test = nested_conditions[0]
                for cond in nested_conditions[1:]:
                    nested_test = cst.BooleanOperation(
                        left=nested_test,
                        operator=cst.And(),
                        right=cond
                    )
                
                # Try to extract sequence pattern from nested_test
                nested_result = self._extract_sequence_pattern(nested_test)
                if nested_result:
                    _, nested_patterns = nested_result
                    patterns[idx] = ('sequence', nested_patterns)
        
        def collect_subscript_checks(node: cst.BaseExpression) -> bool:
            """Returns False if pattern is invalid."""
            
            # Check for isinstance(x[i], Class)
            if m.matches(node, m.Call(func=m.Name(value="isinstance"), args=[m.Arg(), m.Arg()])):
                call = node  # type: ignore
                subscript_arg = call.args[0].value
                if m.matches(subscript_arg, m.Subscript()):
                    subscript = subscript_arg  # type: ignore
                    if subscript.value.deep_equals(subject):
                        # Get the index
                        if len(subscript.slice) == 1:
                            slice_elem = subscript.slice[0]
                            if isinstance(slice_elem.slice, cst.Index):
                                index_val = slice_elem.slice.value
                                if m.matches(index_val, m.Integer()):
                                    idx = int(index_val.value)  # type: ignore
                                    if 0 <= idx < expected_len_val:
                                        class_arg = call.args[1].value
                                        # Extract classes (single or tuple)
                                        if isinstance(class_arg, cst.Tuple):
                                            classes = []
                                            for element in class_arg.elements:
                                                if isinstance(element, cst.Element):
                                                    classes.append(element.value)
                                            patterns[idx] = ('isinstance', classes)
                                        else:
                                            patterns[idx] = ('isinstance', [class_arg])
                                        return True
                return True  # Not a valid isinstance on subscript
            
            # Check for x[i] == value or x[i] is value
            elif m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Subscript()):
                    subscript = comp.left  # type: ignore
                    # Verify it's subscripting the same subject
                    if subscript.value.deep_equals(subject):
                        # Get the index
                        if len(subscript.slice) == 1:
                            slice_elem = subscript.slice[0]
                            if isinstance(slice_elem.slice, cst.Index):
                                index_val = slice_elem.slice.value
                                if m.matches(index_val, m.Integer()):
                                    idx = int(index_val.value)  # type: ignore
                                    if 0 <= idx < expected_len_val:
                                        value = comp.comparisons[0].comparator
                                        operator = comp.comparisons[0].operator
                                        
                                        # 'is' operator should only be used with singletons
                                        if isinstance(operator, cst.Is):
                                            if not m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                                                return False
                                        # Only support literal values for '=='
                                        elif not self._is_literal_value(value):
                                            return False
                                        
                                        patterns[idx] = ('literal', value)
                                        return True
                return True  # Not a subscript check, skip it
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                return collect_subscript_checks(bool_op.left) and collect_subscript_checks(bool_op.right)
            # Skip len() checks
            elif m.matches(node, m.Comparison()):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"))):
                    return True
            return True
        
        if not collect_subscript_checks(test):
            return None
        
        # Validate all indices are covered
        if None in patterns:
            return None

        return (subject, patterns)  # type: ignore

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
                
                # Each branch must be either isinstance, isinstance with and, sequence pattern, or equality with literal
                if self._is_isinstance_call(current.test) or self._is_isinstance_with_and(current.test):
                    # isinstance is always valid
                    pass
                elif self._is_sequence_pattern(current.test):
                    # sequence pattern is valid
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
                    # Check if this is a sequence attribute
                    if isinstance(value, tuple) and value[0] == 'sequence':
                        # Build sequence pattern for this attribute
                        _, seq_patterns = value
                        seq_elements = []
                        for j, (pattern_type, pattern_data) in enumerate(seq_patterns):
                            if pattern_type == 'literal':
                                literal_value = pattern_data
                                if m.matches(literal_value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                                    seq_pattern = cst.MatchSingleton(value=literal_value)
                                else:
                                    seq_pattern = cst.MatchValue(value=literal_value)
                            elif pattern_type == 'isinstance':
                                classes = pattern_data
                                if len(classes) == 1:
                                    seq_pattern = cst.MatchClass(cls=classes[0], patterns=[])
                                else:
                                    class_patterns = [cst.MatchClass(cls=cls, patterns=[]) for cls in classes]
                                    seq_pattern = cst.MatchOr(patterns=class_patterns)
                            elif pattern_type == 'sequence':
                                # Recursively handle deeper nesting
                                seq_pattern = self._build_nested_sequence_pattern(pattern_data)
                            else:
                                raise ValueError(f"Unknown pattern type in sequence attribute: {pattern_type}")
                            
                            if j < len(seq_patterns) - 1:
                                seq_elements.append(cst.MatchSequenceElement(
                                    value=seq_pattern,
                                    comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                                ))
                            else:
                                seq_elements.append(cst.MatchSequenceElement(value=seq_pattern))
                        
                        pattern = cst.MatchList(
                            patterns=seq_elements,
                            lbracket=cst.LeftSquareBracket(),
                            rbracket=cst.RightSquareBracket(),
                        )
                    else:
                        # Create MatchKeywordElement for scalar attribute
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
            elif self._is_sequence_pattern(current.test):
                # len(x) == N and x[0] == val0 and x[1] == val1 ... -> case [val0, val1, ...]:
                result = self._extract_sequence_pattern(current.test)
                if result is None:
                    return updated_node
                _, patterns = result
                
                # Build sequence pattern elements
                elements = []
                for i, (pattern_type, pattern_data) in enumerate(patterns):
                    # Create pattern based on type
                    if pattern_type == 'literal':
                        value = pattern_data
                        if m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                            pattern = cst.MatchSingleton(value=value)
                        else:
                            pattern = cst.MatchValue(value=value)
                    elif pattern_type == 'isinstance':
                        # pattern_data is a list of class expressions
                        classes = pattern_data
                        if len(classes) == 1:
                            # Single class: isinstance(x[i], Point) -> Point()
                            pattern = cst.MatchClass(cls=classes[0], patterns=[])
                        else:
                            # Multiple classes: isinstance(x[i], (Point, Line)) -> Point() | Line()
                            class_patterns = [cst.MatchClass(cls=cls, patterns=[]) for cls in classes]
                            pattern = cst.MatchOr(patterns=class_patterns)
                    elif pattern_type == 'sequence':
                        # Nested sequence pattern - recursively build it
                        nested_patterns = pattern_data
                        nested_elements = []
                        for j, (nested_type, nested_data) in enumerate(nested_patterns):
                            if nested_type == 'literal':
                                value = nested_data
                                if m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")):
                                    nested_pattern = cst.MatchSingleton(value=value)
                                else:
                                    nested_pattern = cst.MatchValue(value=value)
                            elif nested_type == 'isinstance':
                                classes = nested_data
                                if len(classes) == 1:
                                    nested_pattern = cst.MatchClass(cls=classes[0], patterns=[])
                                else:
                                    class_patterns = [cst.MatchClass(cls=cls, patterns=[]) for cls in classes]
                                    nested_pattern = cst.MatchOr(patterns=class_patterns)
                            elif nested_type == 'sequence':
                                # Recursively handle deeper nesting - need a helper function
                                nested_pattern = self._build_nested_sequence_pattern(nested_data)
                            else:
                                raise ValueError(f"Unknown nested pattern type: {nested_type}")
                            
                            if j < len(nested_patterns) - 1:
                                nested_elements.append(cst.MatchSequenceElement(
                                    value=nested_pattern,
                                    comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                                ))
                            else:
                                nested_elements.append(cst.MatchSequenceElement(value=nested_pattern))
                        # Nested sequence needs explicit brackets: [1, 2]
                        pattern = cst.MatchList(
                            patterns=nested_elements,
                            lbracket=cst.LeftSquareBracket(),
                            rbracket=cst.RightSquareBracket(),
                        )
                    else:
                        raise ValueError(f"Unknown pattern type: {pattern_type}")
                    
                    # Add comma for all but the last element
                    if i < len(patterns) - 1:
                        elements.append(cst.MatchSequenceElement(
                            value=pattern,
                            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                        ))
                    else:
                        elements.append(cst.MatchSequenceElement(value=pattern))
                
                # Use MatchList WITHOUT brackets for comma-separated patterns
                # This creates: case [1, 2], 3: (not case [[1, 2], 3]:)
                case_pattern = cst.MatchList(
                    patterns=elements,
                    lbracket=None,  # No outer brackets
                    rbracket=None,
                )
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