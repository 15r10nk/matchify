"""Second-pass capture-pattern rewrite."""

from __future__ import annotations

import libcst as cst

from .subject_path import (
    AttributePathPart,
    SubjectPath,
    SubjectPathPart,
    SubscriptPathPart,
)

CapturePath = tuple[SubjectPathPart, ...]


class CapturePatternTransformer(cst.CSTTransformer):
    """Second-pass transformer that adds capture patterns to match statements.

    This transformer looks for match statements where the case body starts with
    an assignment like `var = subject.attr[index]` and converts it to a capture
    pattern like `case Point(attr=[var, *_]):`.
    """

    def leave_Match(
        self, original_node: cst.Match, updated_node: cst.Match
    ) -> cst.Match:
        """Process match statements to add capture patterns."""
        new_cases = []

        for case in updated_node.cases:
            # Check if this is a pattern shape that can contain class captures.
            if not isinstance(
                case.pattern, (cst.MatchClass, cst.MatchOr, cst.MatchSequence)
            ):
                new_cases.append(case)
                continue

            # Check if body starts with assignments
            if not isinstance(case.body, cst.IndentedBlock):
                new_cases.append(case)
                continue

            # Detect multiple capture assignments at the start of the body
            captures = self._detect_multiple_captures(case.body, updated_node.subject)
            if not captures:
                new_cases.append(case)
                continue

            # Group captures by attribute
            captures_by_path = {}
            for var_name, capture_path, index in captures:
                if capture_path not in captures_by_path:
                    captures_by_path[capture_path] = []
                captures_by_path[capture_path].append((var_name, capture_path, index))

            # Try to add captures for each attribute
            new_pattern = case.pattern
            for capture_path, attr_captures in captures_by_path.items():
                new_pattern = self._add_multiple_captures_to_pattern(
                    new_pattern, capture_path, attr_captures
                )
                if new_pattern is None:
                    break

            if new_pattern is None:
                new_cases.append(case)
                continue

            # Remove the assignment statements from the body
            new_body = self._remove_statements(case.body, len(captures))

            # Create new case with capture pattern and updated body
            new_case = case.with_changes(pattern=new_pattern, body=new_body)
            new_cases.append(new_case)

        return updated_node.with_changes(cases=new_cases)

    def _detect_multiple_captures(
        self, body: cst.IndentedBlock, subject: cst.BaseExpression
    ) -> list[tuple[str, CapturePath, int]]:
        """Detect multiple consecutive capture assignments at the start of body.

        Returns:
            List of (var_name, capture_path, index) tuples, one for each capture assignment.
            Empty list if no valid captures found.
        """
        captures = []

        for stmt in body.body:
            # Must be a simple statement line with a single assignment
            if not isinstance(stmt, cst.SimpleStatementLine):
                break

            if len(stmt.body) != 1 or not isinstance(stmt.body[0], cst.Assign):
                break

            assign = stmt.body[0]
            capture_info = self._detect_capture_assignment(assign, subject)

            if capture_info is None:
                break

            captures.append(capture_info)

        return captures

    def _detect_capture_assignment(
        self, assign: cst.Assign, subject: cst.BaseExpression
    ) -> tuple[str, CapturePath, int] | None:
        """Detect if assignment is like: var = subject.attr[index].

        Returns:
            Tuple of (var_name, capture_path, index) or None if not matching pattern
        """
        # Check target is a simple name
        if len(assign.targets) != 1:
            return None

        target = assign.targets[0].target
        if not isinstance(target, cst.Name):
            return None

        var_name = target.value

        # Check value is a subscript
        if not isinstance(assign.value, cst.Subscript):
            return None

        subscript = assign.value

        # Check subscript is on an attribute of the subject
        if not isinstance(subscript.value, cst.Attribute):
            return None

        path = SubjectPath.from_expression(subscript.value, subject)
        if path is None or not path.parts:
            return None
        capture_path = path.parts

        # Check index is an integer literal
        if not isinstance(subscript.slice[0].slice, cst.Index):
            return None

        index_node = subscript.slice[0].slice.value
        if not isinstance(index_node, cst.Integer):
            return None

        index = int(index_node.value)

        return (var_name, capture_path, index)

    def _add_multiple_captures_to_pattern(
        self,
        pattern: cst.MatchPattern,
        capture_path: CapturePath,
        captures: list[tuple[str, CapturePath, int]],
    ) -> cst.MatchPattern | None:
        """Add multiple capture patterns to the specified attribute.

        Transforms a pattern like Point(x=[_]) to Point(x=[first, second, *_])
        when captures = [('first', 'x', 0), ('second', 'x', 1)].

        Supports non-consecutive indices by inserting wildcards:
        captures = [('first', 'x', 0), ('third', 'x', 2)] → Point(x=[first, _, third, *_])

        Supports indices not starting from 0:
        captures = [('second', 'x', 1), ('third', 'x', 2)] → Point(x=[_, second, third, *_])
        """
        if not capture_path:
            return None

        if isinstance(pattern, cst.MatchOr):
            return self._add_captures_to_or_pattern(pattern, capture_path, captures)

        first_part = capture_path[0]
        remaining_path = capture_path[1:]

        if isinstance(first_part, SubscriptPathPart):
            return self._add_subscript_captures_to_pattern(
                pattern, first_part, remaining_path, captures
            )

        if not isinstance(pattern, cst.MatchClass) or not isinstance(
            first_part, AttributePathPart
        ):
            return None

        if remaining_path:
            return self._add_nested_captures_to_pattern(
                pattern, first_part.name, remaining_path, captures
            )

        attr_name = first_part.name

        # Get indices and sort captures by index
        indices = [idx for _, _, idx in captures]
        sorted_captures = sorted(captures, key=lambda c: c[2])

        # Validate no duplicate indices
        if len(indices) != len(set(indices)):
            # Duplicate indices
            return None

        # Get max index
        max_index = max(indices)

        # Find the attribute in the pattern
        new_kwds = []
        found = False

        for kwd in pattern.kwds:
            if not isinstance(kwd, cst.MatchKeywordElement):
                new_kwds.append(kwd)
                continue

            # Check if this is the attribute we're looking for
            if not isinstance(kwd.pattern, cst.MatchSequence):
                new_kwds.append(kwd)
                continue

            if kwd.key.value != attr_name:
                new_kwds.append(kwd)
                continue

            # Found it! Build new sequence with captures (supporting non-consecutive indices)
            seq_pattern = kwd.pattern
            elements = list(seq_pattern.patterns)

            # Build pattern elements from 0 to max_index
            # For each position: either a capture or a wildcard
            capture_map = {idx: var_name for var_name, _, idx in sorted_captures}

            new_elements = []
            for i in range(max_index + 1):
                if i in capture_map:
                    # This index has a capture
                    capture_elem = cst.MatchSequenceElement(
                        value=cst.MatchAs(pattern=None, name=cst.Name(capture_map[i])),
                        comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
                    )
                    new_elements.append(capture_elem)
                else:
                    # This index doesn't have a capture, use wildcard
                    wildcard_elem = cst.MatchSequenceElement(
                        value=cst.MatchAs(pattern=None, name=None),
                        comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
                    )
                    new_elements.append(wildcard_elem)

            # Check if original pattern has wildcards or if we need to add star
            all_wildcards = all(
                isinstance(el.value, cst.MatchAs)
                and el.value.pattern is None
                and el.value.name is None
                for el in elements
            )

            # Add star pattern at the end to match remaining elements
            if all_wildcards or len(elements) > len(new_elements):
                star_element = cst.MatchSequenceElement(
                    value=cst.MatchStar(name=cst.Name("_"))
                )
                new_elements.append(star_element)
            else:
                # Keep any remaining elements from original pattern
                remaining_elements = elements[len(new_elements) :]
                new_elements.extend(remaining_elements)

            new_seq_pattern = seq_pattern.with_changes(patterns=new_elements)
            new_kwd = kwd.with_changes(pattern=new_seq_pattern)
            new_kwds.append(new_kwd)
            found = True

        if not found:
            return None

        return pattern.with_changes(kwds=new_kwds)

    def _add_captures_to_or_pattern(
        self,
        pattern: cst.MatchOr,
        capture_path: CapturePath,
        captures: list[tuple[str, CapturePath, int]],
    ) -> cst.MatchOr | None:
        elements = []
        for element in pattern.patterns:
            if not isinstance(element.pattern, cst.MatchClass):
                return None
            new_pattern = self._add_multiple_captures_to_pattern(
                element.pattern, capture_path, captures
            )
            if new_pattern is None or not isinstance(new_pattern, cst.MatchClass):
                return None
            elements.append(element.with_changes(pattern=new_pattern))
        return pattern.with_changes(patterns=elements)

    def _add_subscript_captures_to_pattern(
        self,
        pattern: cst.MatchPattern,
        subscript_part: SubscriptPathPart,
        remaining_path: CapturePath,
        captures: list[tuple[str, CapturePath, int]],
    ) -> cst.MatchPattern | None:
        if (
            not isinstance(pattern, cst.MatchSequence)
            or subscript_part.index is None
            or subscript_part.index >= len(pattern.patterns)
        ):
            return None

        elements = list(pattern.patterns)
        element = elements[subscript_part.index]
        new_element_pattern = self._add_multiple_captures_to_pattern(
            element.value, remaining_path, captures
        )
        if new_element_pattern is None:
            return None

        elements[subscript_part.index] = element.with_changes(value=new_element_pattern)
        return pattern.with_changes(patterns=elements)

    def _add_nested_captures_to_pattern(
        self,
        pattern: cst.MatchClass,
        attr_name: str,
        remaining_path: CapturePath,
        captures: list[tuple[str, CapturePath, int]],
    ) -> cst.MatchClass | None:
        new_kwds = []
        found = False

        for kwd in pattern.kwds:
            if not isinstance(kwd, cst.MatchKeywordElement):
                new_kwds.append(kwd)
                continue

            if kwd.key.value != attr_name:
                new_kwds.append(kwd)
                continue

            if not isinstance(kwd.pattern, cst.MatchClass):
                new_kwds.append(kwd)
                continue

            nested_pattern = self._add_multiple_captures_to_pattern(
                kwd.pattern, remaining_path, captures
            )
            if nested_pattern is None:
                return None
            new_kwds.append(kwd.with_changes(pattern=nested_pattern))
            found = True

        if not found:
            return None

        return pattern.with_changes(kwds=new_kwds)

    def _remove_statements(
        self, body: cst.IndentedBlock, count: int
    ) -> cst.IndentedBlock:
        """Remove first N statements from body, or replace with pass if it leaves no statements."""
        if len(body.body) <= count:
            # Replace with pass statement
            pass_stmt = cst.SimpleStatementLine(body=[cst.Pass()])
            return body.with_changes(body=[pass_stmt])
        else:
            # Remove first N statements
            return body.with_changes(body=body.body[count:])
