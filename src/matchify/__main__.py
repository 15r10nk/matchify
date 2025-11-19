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
from typing import List, NamedTuple

import libcst as cst
from libcst import matchers as m
from libcst.metadata import PositionProvider


class LiteralPattern(NamedTuple):
    """Represents a literal value pattern like case 1: or case "hello":"""
    value: cst.BaseExpression


class IsinstancePattern(NamedTuple):
    """Represents an isinstance pattern like case int(): or case (int | str):"""
    classes: list[cst.BaseExpression]


class IsinstanceWithAttrsPattern(NamedTuple):
    """Represents an isinstance with attributes pattern like case Point(x=1, y=2):"""
    class_expr: cst.BaseExpression
    attrs: list[tuple[str, cst.BaseExpression | tuple]]


class SequencePattern(NamedTuple):
    """Represents a sequence pattern like case [1, 2, 3]: or case Point(), "hello":"""
    patterns: list


class PatternInfo(NamedTuple):
    """Container for pattern information extracted from if/elif conditions."""
    pattern_type: str  # 'literal', 'isinstance', 'isinstance_with_attrs', 'sequence'
    data: cst.BaseExpression | list[cst.BaseExpression] | tuple


class SequencePatternCollector:
    """Helper class to collect sequence pattern information in a single AST pass."""
    
    def __init__(self, subject: cst.BaseExpression):
        self.subject = subject
        self.expected_len: int | None = None
        self.elements: dict[int, PatternInfo] = {}
        self.nested_sequences: set[int] = set()
        
    def collect_from_node(self, node: cst.BaseExpression) -> bool:
        """Collect pattern information from a single AST node. Returns False if invalid."""
        
        # Check for len(subject) == N
        if self._is_len_check(node):
            if self.expected_len is not None:
                return False  # Multiple len checks
            self.expected_len = self._extract_len_value(node)
            return self.expected_len is not None
            
        # Check for subject[idx] == value or subject[idx] is value
        if self._is_subscript_literal_check(node):
            idx = self._extract_subscript_index(node)
            if idx is None or idx in self.elements:
                return False
            value = self._extract_comparison_value(node)
            if value is None:
                return False
            self.elements[idx] = PatternInfo("literal", value)
            return True
            
        # Check for isinstance(subject[idx], Class)
        if self._is_subscript_isinstance_check(node):
            idx = self._extract_subscript_index(node)
            if idx is None or idx in self.elements:
                return False
            classes = self._extract_isinstance_classes(node)
            if classes is None:
                return False
            self.elements[idx] = PatternInfo("isinstance", classes)
            # Don't mark as nested yet - will be marked later if attributes are found
            return True
            
        # Check for len(subject[idx]) - indicates nested sequence
        if self._is_nested_len_check(node):
            idx = self._extract_nested_index(node)
            if idx is not None:
                self.nested_sequences.add(idx)
            return True
            
        # Check for nested subscript patterns (subject[idx][subidx] == value)
        if self._is_nested_subscript_check(node):
            idx = self._extract_nested_index(node)
            if idx is not None and idx in self.nested_sequences:
                # This will be handled when we process nested sequences
                return True
                
        return True  # Skip unknown patterns
        
    def _is_len_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is len(subject) == N"""
        if not m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
            return False
        comp = node  # type: ignore
        if not self._is_len_call(comp.left):
            return False
        call = comp.left  # type: ignore
        if len(call.args) == 0:
            return False
        return call.args[0].value.deep_equals(self.subject)
        
    def _extract_len_value(self, node: cst.BaseExpression) -> int | None:
        """Extract the expected length from len(subject) == N"""
        comp = node  # type: ignore
        comparator = comp.comparisons[0].comparator
        if m.matches(comparator, m.Integer()):
            return int(comparator.value)  # type: ignore
        return None
        
    def _is_subscript_literal_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is subject[idx] == value or subject[idx] is value"""
        if not m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())])):
            return False
        comp = node  # type: ignore
        if not m.matches(comp.left, m.Subscript()):
            return False
        subscript = comp.left  # type: ignore
        if not subscript.value.deep_equals(self.subject):
            return False
        # Validate the value is a literal/singleton
        value = comp.comparisons[0].comparator
        operator = comp.comparisons[0].operator
        if isinstance(operator, cst.Is):
            return m.matches(value, m.Name(value="None") | m.Name(value="True") | m.Name(value="False"))
        else:
            return self._is_literal_value(value)
            
    def _extract_subscript_index(self, node: cst.BaseExpression) -> int | None:
        """Extract index from subject[idx] in a comparison or isinstance call."""
        # For comparisons: subject[idx] == value
        if m.matches(node, m.Comparison()):
            comp = node  # type: ignore
            if m.matches(comp.left, m.Subscript()):
                subscript = comp.left  # type: ignore
                return self._extract_subscript_index_from_subscript(subscript)
        # For isinstance calls: isinstance(subject[idx], Class)
        elif m.matches(node, m.Call(func=m.Name(value="isinstance"))):
            call = node  # type: ignore
            if len(call.args) >= 1 and m.matches(call.args[0].value, m.Subscript()):
                subscript = call.args[0].value  # type: ignore
                return self._extract_subscript_index_from_subscript(subscript)
        return None
        
    def _extract_subscript_index_from_subscript(self, subscript: cst.Subscript) -> int | None:
        """Extract integer index from a subscript"""
        if len(subscript.slice) == 1:
            slice_elem = subscript.slice[0]
            if isinstance(slice_elem.slice, cst.Index):
                index_val = slice_elem.slice.value
                if m.matches(index_val, m.Integer()):
                    return int(index_val.value)  # type: ignore
        return None
        
    def _extract_comparison_value(self, node: cst.BaseExpression) -> cst.BaseExpression | None:
        """Extract the comparison value from subject[idx] == value"""
        comp = node  # type: ignore
        return comp.comparisons[0].comparator
        
    def _is_subscript_isinstance_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is isinstance(subject[idx], Class)"""
        if not m.matches(node, m.Call(func=m.Name(value="isinstance"))):
            return False
        call = node  # type: ignore
        if len(call.args) < 2:
            return False
        arg = call.args[0].value
        if not m.matches(arg, m.Subscript()):
            return False
        subscript = arg  # type: ignore
        return subscript.value.deep_equals(self.subject)
        
    def _extract_isinstance_classes(self, node: cst.BaseExpression) -> list[cst.BaseExpression] | None:
        """Extract classes from isinstance(subject[idx], Class) or isinstance(subject[idx], (Class1, Class2))"""
        call = node  # type: ignore
        class_arg = call.args[1].value
        
        if isinstance(class_arg, cst.Tuple):
            classes = []
            for element in class_arg.elements:
                if isinstance(element, cst.Element):
                    classes.append(element.value)
                else:
                    return None  # Starred elements not supported
            return classes if classes else None
        else:
            return [class_arg]
            
    def _is_nested_len_check(self, node: cst.BaseExpression) -> bool:
        """Check if node is len(subject[idx]) == N"""
        if not m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
            return False
        comp = node  # type: ignore
        if not self._is_len_call(comp.left):
            return False
        call = comp.left  # type: ignore
        if len(call.args) == 0:
            return False
        len_arg = call.args[0].value
        if not m.matches(len_arg, m.Subscript()):
            return False
        subscript = len_arg  # type: ignore
        return subscript.value.deep_equals(self.subject)
        
    def _extract_nested_index(self, node: cst.BaseExpression) -> int | None:
        """Extract the index from len(subject[idx]) or subject[idx][...]"""
        comp = node  # type: ignore
        left = comp.left
        
        if self._is_len_call(left):
            call = left  # type: ignore
            len_arg = call.args[0].value
            subscript = len_arg  # type: ignore
        else:
            subscript = left  # type: ignore
            
        return self._extract_subscript_index_from_subscript(subscript)
        
    def _is_nested_subscript_check(self, node: cst.BaseExpression) -> bool:
        """Check if node involves subject[idx][subidx]"""
        if not m.matches(node, m.Comparison()):
            return False
        comp = node  # type: ignore
        if not m.matches(comp.left, m.Subscript()):
            return False
        subscript = comp.left  # type: ignore
        if not m.matches(subscript.value, m.Subscript()):
            return False
        inner_subscript = subscript.value  # type: ignore
        return inner_subscript.value.deep_equals(self.subject)
        
    def _is_literal_value(self, node: cst.BaseExpression) -> bool:
        """Check if a node is a literal value (copied from main class)"""
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
            | m.Name(value="None"),
        )
        
    def _is_len_call(self, node: cst.BaseExpression) -> bool:
        """Check if node is a len() call (copied from main class)"""
        return m.matches(node, m.Call(func=m.Name(value="len"), args=[m.Arg()]))


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

            def find_isinstance_subject(
                node: cst.BaseExpression,
            ) -> cst.BaseExpression | None:
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
            | m.Name(value="None"),
        )

    def _extract_subscript_index(self, subscript: cst.Subscript) -> int | None:
        """Extract integer index from a subscript like x[0] or x[1].

        Args:
            subscript: A Subscript node

        Returns:
            The integer index if it's a simple integer subscript, None otherwise
        """
        if len(subscript.slice) == 1:
            slice_elem = subscript.slice[0]
            if isinstance(slice_elem.slice, cst.Index):
                index_val = slice_elem.slice.value
                if m.matches(index_val, m.Integer()):
                    return int(index_val.value)  # type: ignore
        return None

    def _traverse_boolean_and(self, node: cst.BaseExpression, predicate) -> bool:
        """Recursively traverse BooleanOperation(And) tree and check if predicate matches any node.
        
        Args:
            node: The node to check
            predicate: A callable that takes a node and returns bool
            
        Returns:
            True if predicate matches any node in the tree
        """
        if predicate(node):
            return True
        if m.matches(node, m.BooleanOperation(operator=m.And())):
            bool_op = node  # type: ignore
            return self._traverse_boolean_and(bool_op.left, predicate) or self._traverse_boolean_and(bool_op.right, predicate)
        return False
    
    def _find_in_boolean_and(self, node: cst.BaseExpression, predicate) -> cst.BaseExpression | None:
        """Recursively traverse BooleanOperation(And) tree and return first node matching predicate.
        
        Args:
            node: The node to search
            predicate: A callable that takes a node and returns bool
            
        Returns:
            First matching node or None
        """
        if predicate(node):
            return node
        if m.matches(node, m.BooleanOperation(operator=m.And())):
            bool_op = node  # type: ignore
            result = self._find_in_boolean_and(bool_op.left, predicate)
            if result is not None:
                return result
            return self._find_in_boolean_and(bool_op.right, predicate)
        return None

    def _is_isinstance_call(self, test: cst.BaseExpression) -> bool:
        """Check if test is an isinstance(subject, type) call."""
        return m.matches(
            test,
            m.Call(
                func=m.Name(value="isinstance"),
                args=[m.Arg(), m.Arg()],
            ),
        )

    def _is_len_call(self, node: cst.BaseExpression) -> bool:
        """Check if node is a len() call."""
        return m.matches(node, m.Call(func=m.Name(value="len"), args=[m.Arg()]))

    def _is_singleton_name(self, node: cst.BaseExpression) -> bool:
        """Check if node is None, True, or False."""
        return m.matches(
            node, m.Name(value="None") | m.Name(value="True") | m.Name(value="False")
        )

    def _is_subscript_of_subject(
        self, node: cst.BaseExpression, subject: cst.BaseExpression, index: int
    ) -> bool:
        """Check if node is subject[index]."""
        if not m.matches(node, m.Subscript()):
            return False
        subscript = node  # type: ignore
        if not subscript.value.deep_equals(subject):
            return False
        idx = self._extract_subscript_index(subscript)
        return idx == index

    def _is_isinstance_with_and(self, test: cst.BaseExpression) -> bool:
        """Check if test is isinstance(subject, type) and subject.attr == value.
        
        This should NOT match sequence patterns that happen to contain isinstance elements.
        We distinguish by checking if isinstance is on the subject itself (not subject[idx]).
        """
        if not m.matches(test, m.BooleanOperation(operator=m.And())):
            return False

        def is_isinstance_on_subject(node: cst.BaseExpression) -> bool:
            if self._is_isinstance_call(node):
                call = node  # type: ignore
                if len(call.args) >= 1:
                    isinstance_arg = call.args[0].value
                    # Only match if argument is NOT a subscript (not subject[idx])
                    return not m.matches(isinstance_arg, m.Subscript())
            return False

        return self._traverse_boolean_and(test, is_isinstance_on_subject)

    def _extract_isinstance_classes(
        self, test: cst.BaseExpression
    ) -> list[cst.BaseExpression] | None:
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

    def _build_match_or_from_classes(
        self, classes: list[cst.BaseExpression]
    ) -> cst.MatchClass | cst.MatchOr:
        """Build a MatchOr pattern from multiple class expressions.
        
        For single class: returns MatchClass(cls=Class, patterns=[])
        For multiple classes: returns MatchOr with Class1() | Class2() | ...\
        
        Args:
            classes: List of class expressions
            
        Returns:
            A MatchClass or MatchOr pattern node
        """
        if len(classes) == 1:
            return cst.MatchClass(cls=classes[0], patterns=[])

        # Multiple classes need MatchOrElement wrappers with separators
        or_elements = []
        for i, cls in enumerate(classes):
            match_class = cst.MatchClass(cls=cls, patterns=[])
            if i < len(classes) - 1:
                or_elements.append(
                    cst.MatchOrElement(pattern=match_class, separator=cst.BitOr())
                )
            else:
                or_elements.append(cst.MatchOrElement(pattern=match_class))
        return cst.MatchOr(patterns=or_elements)

    def _build_pattern_from_value(
        self, value: cst.BaseExpression
    ) -> cst.MatchSingleton | cst.MatchValue:
        """Build a match pattern from a literal value.

        Args:
            value: The literal value expression

        Returns:
            MatchSingleton for None/True/False, MatchValue for other literals
        """
        if self._is_singleton_name(value):
            return cst.MatchSingleton(value=value)
        else:
            return cst.MatchValue(value=value)

    def _build_class_pattern_keywords(
        self, attrs: list[tuple[str, cst.BaseExpression | tuple[str, list[PatternInfo]]]]
    ) -> list[cst.MatchKeywordElement]:
        """Build keyword arguments for a MatchClass pattern.

        Args:
            attrs: List of (attr_name, value) tuples where value is either:
                   - A CST expression node for scalar attributes
                   - A tuple ('sequence', patterns) for sequence attributes

        Returns:
            List of MatchKeywordElement nodes
        """
        kwds = []
        for attr_name, value in attrs:
            # Check if this is a sequence attribute
            if isinstance(value, tuple) and value[0] == "sequence":
                # Build sequence pattern for this attribute
                _, seq_patterns = value
                pattern = self._build_sequence_pattern_for_attr(seq_patterns)
            else:
                # Scalar attribute - create literal/singleton pattern
                pattern = self._build_pattern_from_value(value)

            kwds.append(
                cst.MatchKeywordElement(key=cst.Name(attr_name), pattern=pattern)
            )
        return kwds

    def _build_pattern_from_info(self, pattern_info) -> cst.MatchPattern:
        """Build a match pattern from a PatternInfo object or legacy tuple.

        Args:
            pattern_info: PatternInfo object or legacy tuple containing pattern type and data

        Returns:
            A match pattern node
        """
        # Handle legacy tuple format for backward compatibility
        if isinstance(pattern_info, tuple):
            pattern_type, data = pattern_info
        else:
            pattern_type = pattern_info.pattern_type
            data = pattern_info.data

        if pattern_type == "literal":
            assert isinstance(data, cst.BaseExpression)
            return self._build_pattern_from_value(data)
        elif pattern_type == "isinstance":
            assert isinstance(data, list)
            return self._build_match_or_from_classes(data)
        elif pattern_type == "isinstance_with_attrs":
            class_expr, attrs = data
            assert isinstance(class_expr, cst.BaseExpression)
            assert isinstance(attrs, list)
            kwds = self._build_class_pattern_keywords(attrs)
            return cst.MatchClass(cls=class_expr, patterns=[], kwds=kwds)
        elif pattern_type == "sequence":
            assert isinstance(data, list)
            return self._build_nested_sequence_pattern(data)
        else:
            raise ValueError(f"Unknown pattern type: {pattern_type}")

    def _build_sequence_elements(
        self, patterns: list[PatternInfo]
    ) -> list[cst.MatchSequenceElement]:
        """Build a list of MatchSequenceElement nodes from pattern info list.

        Args:
            patterns: List of PatternInfo objects

        Returns:
            List of MatchSequenceElement nodes with proper comma separators
        """
        elements = []
        for i, pattern_info in enumerate(patterns):
            pattern = self._build_pattern_from_info(pattern_info)

            if i < len(patterns) - 1:
                elements.append(
                    cst.MatchSequenceElement(
                        value=pattern,
                        comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
                    )
                )
            else:
                elements.append(cst.MatchSequenceElement(value=pattern))

        return elements

    def _build_case_pattern_from_test(
        self, test: cst.BaseExpression
    ) -> cst.MatchPattern | None:
        """Build a match case pattern from an if/elif test expression.

        Args:
            test: The test expression from an if/elif statement

        Returns:
            A match pattern node, or None if the pattern cannot be built
        """
        if self._is_isinstance_with_and(test):
            # isinstance(subject, Class) and subject.attr == value -> case Class(attr=value):
            result = self._extract_isinstance_with_attrs(test)
            if result is None:
                return None
            class_expr, attrs = result

            kwds = self._build_class_pattern_keywords(attrs)
            return cst.MatchClass(cls=class_expr, patterns=[], kwds=kwds)

        elif self._is_isinstance_call(test):
            # isinstance(subject, Class) -> case Class():
            # isinstance(subject, (Class1, Class2)) -> case Class1() | Class2():
            class_exprs = self._extract_isinstance_classes(test)
            if class_exprs is None:
                return None
            return self._build_match_or_from_classes(class_exprs)

        elif self._is_sequence_pattern(test):
            # len(x) == N and x[0] == val0 and x[1] == val1 ... -> case [val0, val1, ...]:
            result = self._extract_sequence_pattern(test)
            if result is None:
                return None
            _, patterns = result

            # Build sequence pattern elements using helper
            elements = self._build_sequence_elements(patterns)

            # Use MatchList WITHOUT brackets for comma-separated patterns
            # This creates: case [1, 2], 3: (not case [[1, 2], 3]:)
            return cst.MatchList(
                patterns=elements,
                lbracket=None,  # No outer brackets
                rbracket=None,
            )

        else:
            # subject == value -> case value:
            comparator = test.comparisons[0].comparator  # type: ignore
            return self._build_pattern_from_value(comparator)

    def _build_sequence_pattern_for_attr(self, seq_patterns: list[PatternInfo]) -> cst.MatchList:
        """Build a sequence pattern for a class attribute.

        Used for patterns like Data(value=[1, 2, 3]) where value is a sequence attribute.
        """
        seq_elements = self._build_sequence_elements(seq_patterns)
        return cst.MatchList(
            patterns=seq_elements,
            lbracket=cst.LeftSquareBracket(),
            rbracket=cst.RightSquareBracket(),
        )

    def _build_nested_sequence_pattern(self, patterns: list[PatternInfo]) -> cst.MatchList:
        """Recursively build a nested sequence pattern from pattern metadata.

        Args:
            patterns: List of PatternInfo objects

        Returns:
            A MatchList node containing the nested patterns
        """
        elements = self._build_sequence_elements(patterns)
        # Return MatchList WITH brackets for nested sequences
        return cst.MatchList(
            patterns=elements,
            lbracket=cst.LeftSquareBracket(),
            rbracket=cst.RightSquareBracket(),
        )

    def _find_isinstance_call(self, node: cst.BaseExpression) -> cst.Call | None:
        """Find the isinstance call in a potentially nested BooleanOperation."""
        return self._find_in_boolean_and(node, self._is_isinstance_call)  # type: ignore

    def _find_sequence_attrs(self, test: cst.BaseExpression, subject: cst.BaseExpression) -> dict[str, bool]:
        """Find attributes that are checked as sequences."""
        sequence_attrs: dict[str, bool] = {}

        def find_sequence_attrs_recursive(node: cst.BaseExpression) -> None:
            if m.matches(
                node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])
            ):
                comp = node  # type: ignore
                # Check for len(subject.attr) == N
                if self._is_len_call(comp.left):
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
                find_sequence_attrs_recursive(and_op.left)
                find_sequence_attrs_recursive(and_op.right)

        find_sequence_attrs_recursive(test)
        return sequence_attrs

    def _collect_attr_conditions(
        self, test: cst.BaseExpression, subject: cst.BaseExpression, attr_name: str
    ) -> list[cst.BaseExpression]:
        """Collect all conditions related to subject.attr sequence."""
        attr_conditions = []

        def collect_attr_conditions_recursive(node: cst.BaseExpression) -> None:
            if m.matches(
                node,
                m.Comparison(
                    comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())]
                ),
            ):
                comp = node  # type: ignore
                # Check for len(subject.attr) == N or len(subject.attr[i].nested_attr)
                if self._is_len_call(comp.left):
                    call = comp.left  # type: ignore
                    if len(call.args) > 0:
                        len_arg = call.args[0].value
                        if m.matches(len_arg, m.Attribute()):
                            attr_expr = len_arg  # type: ignore
                            # Check for simple case: len(subject.attr)
                            if (
                                attr_expr.value.deep_equals(subject)
                                and attr_expr.attr.value == attr_name
                            ):
                                attr_conditions.append(node)
                                return
                            # Check for nested case: len(subject.attr[i].nested_attr)
                            if m.matches(attr_expr.value, m.Subscript()):
                                inner_subscript = attr_expr.value  # type: ignore
                                if m.matches(inner_subscript.value, m.Attribute()):
                                    base_attr = inner_subscript.value  # type: ignore
                                    if (
                                        base_attr.value.deep_equals(subject)
                                        and base_attr.attr.value == attr_name
                                    ):
                                        attr_conditions.append(node)
                                        return
                # Check for subject.attr[i] == value
                if m.matches(comp.left, m.Subscript()):
                    subscript = comp.left  # type: ignore
                    if m.matches(subscript.value, m.Attribute()):
                        attr_expr = subscript.value  # type: ignore
                        # Simple case: subject.attr[i]
                        if (
                            attr_expr.value.deep_equals(subject)
                            and attr_expr.attr.value == attr_name
                        ):
                            attr_conditions.append(node)
                            return
                        # Check if this is subject.attr[i].nested_attr[j] (deeper nesting)
                        if m.matches(attr_expr.value, m.Subscript()):
                            inner_subscript = attr_expr.value  # type: ignore
                            if m.matches(inner_subscript.value, m.Attribute()):
                                base_attr = inner_subscript.value  # type: ignore
                                if (
                                    base_attr.value.deep_equals(subject)
                                    and base_attr.attr.value == attr_name
                                ):
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
                            if (
                                attr_expr.value.deep_equals(subject)
                                and attr_expr.attr.value == attr_name
                            ):
                                attr_conditions.append(node)
                                return
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                and_op = node  # type: ignore
                collect_attr_conditions_recursive(and_op.left)
                collect_attr_conditions_recursive(and_op.right)

        collect_attr_conditions_recursive(test)
        return attr_conditions

    def _extract_attr_checks(
        self, test: cst.BaseExpression, subject: cst.BaseExpression, sequence_attrs: dict[str, bool]
    ) -> list[tuple[str, cst.BaseExpression | tuple[str, list[PatternInfo]]]] | None:
        """Extract attribute checks from the test expression.
        
        Returns None if invalid patterns are found (e.g., non-literal values).
        """
        attrs = []

        # For each sequence attribute, extract its pattern
        for attr_name in sequence_attrs:
            attr_conditions = self._collect_attr_conditions(test, subject, attr_name)

            if attr_conditions:
                # Build a test expression from these conditions
                attr_test = attr_conditions[0]
                for cond in attr_conditions[1:]:
                    attr_test = cst.BooleanOperation(
                        left=attr_test, operator=cst.And(), right=cond
                    )

                # Extract as a sequence pattern, but the subject is subject.attr
                result = self._extract_sequence_pattern(attr_test)
                if result:
                    _, patterns = result
                    attrs.append((attr_name, ("sequence", patterns)))
                else:
                    # Invalid sequence pattern
                    return None

        # Handle single comparison or chain of and comparisons for scalar attributes
        def extract_attr_checks_recursive(node: cst.BaseExpression) -> bool:
            """Recursively extract attribute checks. Returns False if invalid pattern."""
            # Skip isinstance calls
            if self._is_isinstance_call(node):
                return True

            # Skip len() calls - these are handled by sequence attribute extraction
            if m.matches(
                node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])
            ):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"))):
                    return True

            # Skip checks on subscripted attributes (subject.attr[i] or nested like subject.attr[i].nested_attr[j])
            if m.matches(
                node,
                m.Comparison(
                    comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())]
                ),
            ):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Subscript()):
                    subscript = comp.left  # type: ignore
                    # Direct: subject.attr[i]
                    if m.matches(subscript.value, m.Attribute()):
                        return True
                    # Nested: subject.attr[i].nested[j] - the subscript value is itself an attribute
                    if m.matches(subscript.value, m.Attribute()):
                        inner_attr = subscript.value  # type: ignore
                        if m.matches(inner_attr.value, m.Subscript()):
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
                return extract_attr_checks_recursive(and_op.left) and extract_attr_checks_recursive(
                    and_op.right
                )
            elif m.matches(
                node,
                m.Comparison(
                    comparisons=[m.ComparisonTarget(operator=m.Equal() | m.Is())]
                ),
            ):
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
                            if not m.matches(
                                value,
                                m.Name(value="None")
                                | m.Name(value="True")
                                | m.Name(value="False"),
                            ):
                                return False
                        # Only support literal values for '=='
                        elif not self._is_literal_value(value):
                            return False

                        attrs.append((attr_name, value))
                        return True
            return False

        if not extract_attr_checks_recursive(test):
            return None
        
        return attrs

    def _extract_isinstance_with_attrs_from_call(
        self, test: cst.BaseExpression, isinstance_call: cst.Call
    ) -> (
        tuple[
            cst.BaseExpression, list[tuple[str, cst.BaseExpression | tuple[str, list[PatternInfo]]]]
        ]
        | None
    ):
        """Extract class and attribute checks from an isinstance call with additional conditions.

        Returns (class_expr, [(attr_name, value), ...]) or None if not a valid pattern.

        The value can be:
        - A CST expression for simple values: (attr_name, value_expr)
        - A tuple for sequence patterns: (attr_name, ('sequence', pattern_list))
        """
        subject = isinstance_call.args[0].value
        class_arg = isinstance_call.args[1].value

        # Don't support tuple of classes with attributes yet
        if isinstance(class_arg, cst.Tuple):
            return None

        sequence_attrs = self._find_sequence_attrs(test, subject)
        attrs = self._extract_attr_checks(test, subject, sequence_attrs)
        
        if attrs is None:
            return None

        return (class_arg, attrs)

    def _extract_isinstance_with_attrs(
        self, test: cst.BaseExpression
    ) -> (
        tuple[
            cst.BaseExpression, list[tuple[str, cst.BaseExpression | tuple[str, list[PatternInfo]]]]
        ]
        | None
    ):
        """Extract class and attribute checks from isinstance(subject, Class) and subject.attr == value.

        Returns (class_expr, [(attr_name, value), ...]) or None if not a valid pattern.
        """
        if not self._is_isinstance_with_and(test):
            return None

        isinstance_call = self._find_isinstance_call(test)
        if isinstance_call is None:
            return None

        return self._extract_isinstance_with_attrs_from_call(test, isinstance_call)

    def _is_sequence_pattern(self, test: cst.BaseExpression) -> bool:
        """Check if test matches: len(x) == N and x[0] == val0 and x[1] == val1 ..."""
        if not m.matches(test, m.BooleanOperation(operator=m.And())):
            return False

        # Need to find len(subject) == N check
        def has_len_check(node: cst.BaseExpression) -> bool:
            if m.matches(
                node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])
            ):
                comp = node  # type: ignore
                # Check for len(x) == N
                if self._is_len_call(comp.left):
                    comparator = comp.comparisons[0].comparator
                    return m.matches(comparator, m.Integer())
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                return has_len_check(bool_op.left) or has_len_check(bool_op.right)
            return False

        return has_len_check(test)

    def _extract_sequence_pattern(self, test: cst.BaseExpression) -> (
        tuple[
            cst.BaseExpression,
            list[PatternInfo],
        ]
        | None
    ):
        """Extract subject and pattern info from sequence patterns.

        Handles patterns like:
        - len(x) == N and x[0] == val0 and x[1] == val1 -> (x, [PatternInfo('literal', val0), PatternInfo('literal', val1)])
        - len(x) == N and isinstance(x[0], Class) and x[1] == val -> (x, [PatternInfo('isinstance', Class), PatternInfo('literal', val)])

        Returns (subject, [PatternInfo, ...]) or None if not valid.
        """
        if not self._is_sequence_pattern(test):
            return None

        # Find the subject from the len() check
        subject = self._find_sequence_subject(test)
        if subject is None:
            return None

        # Use the collector to gather all pattern information in a single pass
        collector = SequencePatternCollector(subject)
        if not self._collect_sequence_patterns(test, collector):
            return None

        # Validate we have a complete sequence
        if collector.expected_len is None:
            return None
            
        expected_len = collector.expected_len
        
        # Handle nested sequences first
        for idx in collector.nested_sequences:
            nested_result = self._extract_nested_sequence_pattern(test, subject, idx)
            if nested_result is not None:
                collector.elements[idx] = nested_result
            # If nested_result is None, keep the original pattern (isinstance without attrs)
            
        # Now validate all indices are covered
        if len(collector.elements) != expected_len:
            return None

        # Build the final pattern list in order
        patterns = []
        for i in range(expected_len):
            if i not in collector.elements:
                return None
            patterns.append(collector.elements[i])

        return (subject, patterns)
        
    def _find_sequence_subject(self, test: cst.BaseExpression) -> cst.BaseExpression | None:
        """Find the subject variable from len(subject) == N check."""
        def find_subject_recursive(node: cst.BaseExpression) -> cst.BaseExpression | None:
            if m.matches(
                node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])
            ):
                comp = node  # type: ignore
                if m.matches(
                    comp.left, m.Call(func=m.Name(value="len"), args=[m.Arg()])
                ):
                    call = comp.left  # type: ignore
                    subject = call.args[0].value
                    return subject
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                result = find_subject_recursive(bool_op.left)
                if result is not None:
                    return result
                return find_subject_recursive(bool_op.right)
            return None
            
        return find_subject_recursive(test)
        
    def _isinstance_element_has_attributes(
        self, test: cst.BaseExpression, subject: cst.BaseExpression, idx: int
    ) -> bool:
        """Check if isinstance(subject[idx], Class) has additional attribute conditions."""
        def is_attr_check_for_index(node: cst.BaseExpression) -> bool:
            if not m.matches(node, m.Comparison()):
                return False
            
            comp = node  # type: ignore
            
            # Check for subject[idx].attr comparisons
            if m.matches(comp.left, m.Attribute()):
                attr = comp.left  # type: ignore
                if m.matches(attr.value, m.Subscript()):
                    subscript = attr.value  # type: ignore
                    if (subscript.value.deep_equals(subject) and
                        self._extract_subscript_index(subscript) == idx):
                        return True
            
            # Check for len(subject[idx].attr)
            if m.matches(comp.left, m.Call(func=m.Name(value="len"))):
                call = comp.left  # type: ignore
                if len(call.args) > 0:
                    len_arg = call.args[0].value
                    if m.matches(len_arg, m.Attribute()):
                        attr = len_arg  # type: ignore
                        if m.matches(attr.value, m.Subscript()):
                            subscript = attr.value  # type: ignore
                            if (subscript.value.deep_equals(subject) and
                                self._extract_subscript_index(subscript) == idx):
                                return True
            
            # Check for subject[idx].attr[subidx]
            if m.matches(comp.left, m.Subscript()):
                subscript = comp.left  # type: ignore
                if m.matches(subscript.value, m.Attribute()):
                    attr = subscript.value  # type: ignore
                    if m.matches(attr.value, m.Subscript()):
                        inner_subscript = attr.value  # type: ignore
                        if (inner_subscript.value.deep_equals(subject) and
                            self._extract_subscript_index(inner_subscript) == idx):
                            return True
            
            return False
        
        return self._traverse_boolean_and(test, is_attr_check_for_index)
    
    def _collect_sequence_patterns(self, test: cst.BaseExpression, collector: SequencePatternCollector) -> bool:
        """Collect all pattern information from the test expression."""
        def collect_recursive(node: cst.BaseExpression) -> bool:
            if m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                return collect_recursive(bool_op.left) and collect_recursive(bool_op.right)
            else:
                return collector.collect_from_node(node)
        
        result = collect_recursive(test)
        
        # Second pass: check if isinstance elements have attributes
        # If they do, mark them as nested so they're re-extracted with attributes
        for idx, pattern_info in list(collector.elements.items()):
            if pattern_info.pattern_type == "isinstance":
                if self._isinstance_element_has_attributes(test, collector.subject, idx):
                    collector.nested_sequences.add(idx)
        
        return result
        
    def _is_subscript_isinstance_with_and(self, test: cst.BaseExpression) -> bool:
        """Check if test is isinstance(subscripted_subject, type) and subscripted_subject.attr == value.
        
        This is for patterns like: isinstance(x[0], Class) and x[0].attr == value
        """
        if not m.matches(test, m.BooleanOperation(operator=m.And())):
            return False

        def is_subscript_isinstance(node: cst.BaseExpression) -> bool:
            if self._is_isinstance_call(node):
                call = node  # type: ignore
                if len(call.args) >= 1:
                    isinstance_arg = call.args[0].value
                    # Only match if argument IS a subscript
                    return m.matches(isinstance_arg, m.Subscript())
            return False

        return self._traverse_boolean_and(test, is_subscript_isinstance)

    def _extract_subscript_isinstance_with_attrs(
        self, test: cst.BaseExpression
    ) -> (
        tuple[
            cst.BaseExpression, list[tuple[str, cst.BaseExpression | tuple[str, list[PatternInfo]]]]
        ]
        | None
    ):
        """Extract class and attribute checks from isinstance(subject[idx], Class) and subject[idx].attr == value.

        Returns (class_expr, [(attr_name, value), ...]) or None if not a valid pattern.
        """
        if not self._is_subscript_isinstance_with_and(test):
            return None

        isinstance_call = self._find_isinstance_call(test)
        if isinstance_call is None:
            return None

        return self._extract_isinstance_with_attrs_from_call(test, isinstance_call)

    def _extract_nested_sequence_pattern(
        self, test: cst.BaseExpression, subject: cst.BaseExpression, idx: int
    ) -> PatternInfo | None:
        """Extract a nested pattern for subject[idx].
        
        This can be either a sequence pattern or an isinstance_with_attrs pattern.
        """
        # Collect all conditions related to subject[idx]
        nested_conditions = []
        
        def collect_nested_conditions(node: cst.BaseExpression) -> None:
            # Check for len(subject[idx]) == N (for sequence patterns)
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"))):
                    call = comp.left  # type: ignore
                    if len(call.args) > 0:
                        len_arg = call.args[0].value
                        if m.matches(len_arg, m.Subscript()):
                            subscript = len_arg  # type: ignore
                            if (subscript.value.deep_equals(subject) and 
                                self._extract_subscript_index(subscript) == idx):
                                nested_conditions.append(node)
                                return
                                
            # Check for subject[idx][subidx] patterns (for sequence patterns)
            if m.matches(node, m.Comparison()):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Subscript()):
                    subscript = comp.left  # type: ignore
                    if m.matches(subscript.value, m.Subscript()):
                        inner_subscript = subscript.value  # type: ignore
                        if (inner_subscript.value.deep_equals(subject) and
                            self._extract_subscript_index(inner_subscript) == idx):
                            nested_conditions.append(node)
                            return
                            
            # Check for isinstance(subject[idx], Class) (for isinstance_with_attrs patterns)
            if m.matches(node, m.Call(func=m.Name(value="isinstance"))):
                call = node  # type: ignore
                if len(call.args) >= 1:
                    isinstance_arg = call.args[0].value
                    if m.matches(isinstance_arg, m.Subscript()):
                        subscript = isinstance_arg  # type: ignore
                        if (subscript.value.deep_equals(subject) and
                            self._extract_subscript_index(subscript) == idx):
                            nested_conditions.append(node)
                            return
                            
            # Check for subject[idx].attr patterns (for isinstance_with_attrs patterns)
            if m.matches(node, m.Comparison()):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Attribute()):
                    attr = comp.left  # type: ignore
                    if m.matches(attr.value, m.Subscript()):
                        subscript = attr.value  # type: ignore
                        if (subscript.value.deep_equals(subject) and
                            self._extract_subscript_index(subscript) == idx):
                            nested_conditions.append(node)
                            return
                            
            # Check for len(subject[idx].attr) patterns (for isinstance_with_attrs with sequence attrs)
            if m.matches(node, m.Comparison(comparisons=[m.ComparisonTarget(operator=m.Equal())])):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Call(func=m.Name(value="len"))):
                    call = comp.left  # type: ignore
                    if len(call.args) > 0:
                        len_arg = call.args[0].value
                        if m.matches(len_arg, m.Attribute()):
                            attr = len_arg  # type: ignore
                            if m.matches(attr.value, m.Subscript()):
                                subscript = attr.value  # type: ignore
                                if (subscript.value.deep_equals(subject) and
                                    self._extract_subscript_index(subscript) == idx):
                                    nested_conditions.append(node)
                                    return
                                    
            # Check for subject[idx].attr[subidx] patterns (for isinstance_with_attrs with sequence attrs)
            if m.matches(node, m.Comparison()):
                comp = node  # type: ignore
                if m.matches(comp.left, m.Subscript()):
                    subscript = comp.left  # type: ignore
                    if m.matches(subscript.value, m.Attribute()):
                        attr = subscript.value  # type: ignore
                        if m.matches(attr.value, m.Subscript()):
                            inner_subscript = attr.value  # type: ignore
                            if (inner_subscript.value.deep_equals(subject) and
                                self._extract_subscript_index(inner_subscript) == idx):
                                nested_conditions.append(node)
                                return
                                
            elif m.matches(node, m.BooleanOperation(operator=m.And())):
                bool_op = node  # type: ignore
                collect_nested_conditions(bool_op.left)
                collect_nested_conditions(bool_op.right)

        collect_nested_conditions(test)
        
        if not nested_conditions:
            return None
            
        # Build combined test for the nested pattern
        nested_test = nested_conditions[0]
        for cond in nested_conditions[1:]:
            nested_test = cst.BooleanOperation(
                left=nested_test, operator=cst.And(), right=cond
            )
            
        # Check if this is an isinstance_with_attrs pattern for a subscripted element
        # isinstance(subject[idx], Class) and subject[idx].attr == value
        if self._is_subscript_isinstance_with_and(nested_test):
            result = self._extract_subscript_isinstance_with_attrs(nested_test)
            if result is not None:
                class_expr, attrs = result
                return PatternInfo("isinstance_with_attrs", (class_expr, attrs))
        
        # Otherwise, try to extract as a sequence pattern
        nested_result = self._extract_sequence_pattern(nested_test)
        if nested_result is not None:
            _, nested_patterns = nested_result
            return PatternInfo("sequence", nested_patterns)
            
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

                # Each branch must be either isinstance, isinstance with and, sequence pattern, or equality with literal
                if self._is_isinstance_call(
                    current.test
                ) or self._is_isinstance_with_and(current.test):
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
                        if not self._is_singleton_name(comparator):
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
    ) -> (
        cst.BaseStatement | cst.FlattenSentinel[cst.BaseStatement] | cst.RemovalSentinel
    ):
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
            case_pattern = self._build_case_pattern_from_test(current.test)
            if case_pattern is None:
                return updated_node

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
        help="Python files or directories to process",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help="Number of parallel jobs (default: number of CPU cores)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show files with no changes"
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
            future_to_path = {
                executor.submit(convert_file, path): path for path in python_files
            }

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
    print(
        f"\nSummary: {converted_count} converted, {unchanged_count} unchanged, {error_count} errors"
    )


if __name__ == "__main__":
    main()
