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

            captures, aliases = self._normalize_duplicate_captures(captures)

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

            # Remove the original assignment statements from the body and keep
            # duplicate reads as aliases to the first captured name.
            new_body = self._remove_statements(case.body, len(captures) + len(aliases))
            if aliases:
                new_body = self._prepend_aliases(new_body, aliases)

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

    def _normalize_duplicate_captures(
        self, captures: list[tuple[str, CapturePath, int]]
    ) -> tuple[list[tuple[str, CapturePath, int]], list[tuple[str, str]]]:
        """Keep one pattern capture per source index and alias later duplicates."""
        seen: dict[tuple[CapturePath, int], str] = {}
        unique_captures = []
        aliases = []

        for var_name, capture_path, index in captures:
            key = (capture_path, index)
            if key in seen:
                aliases.append((var_name, seen[key]))
                continue
            seen[key] = var_name
            unique_captures.append((var_name, capture_path, index))

        return unique_captures, aliases

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

        path = SubjectPath.from_expression(subscript.value, subject)
        if path is None:
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
        if isinstance(pattern, cst.MatchOr):
            return self._add_captures_to_or_pattern(pattern, capture_path, captures)

        if not capture_path:
            if isinstance(pattern, cst.MatchSequence):
                return self._add_captures_to_sequence_pattern(pattern, captures)
            return None

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

        # Find the attribute in the pattern
        new_kwds = []
        found = False

        for kwd in pattern.kwds:
            if not isinstance(kwd, cst.MatchKeywordElement):
                new_kwds.append(kwd)
                continue

            if kwd.key.value != attr_name:
                new_kwds.append(kwd)
                continue

            # Check if this is the attribute we're looking for
            if isinstance(kwd.pattern, cst.MatchOr):
                new_or_pattern = self._add_captures_to_or_pattern(
                    kwd.pattern, (), captures
                )
                if new_or_pattern is None:
                    return None
                new_kwds.append(kwd.with_changes(pattern=new_or_pattern))
                found = True
                continue

            if not isinstance(kwd.pattern, cst.MatchSequence):
                new_kwds.append(kwd)
                continue

            new_seq_pattern = self._add_captures_to_sequence_pattern(
                kwd.pattern, captures
            )
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
            if not isinstance(element.pattern, (cst.MatchClass, cst.MatchSequence)):
                return None
            new_pattern = self._add_multiple_captures_to_pattern(
                element.pattern, capture_path, captures
            )
            if new_pattern is None or not isinstance(
                new_pattern, (cst.MatchClass, cst.MatchSequence)
            ):
                return None
            elements.append(element.with_changes(pattern=new_pattern))
        return pattern.with_changes(patterns=elements)

    def _add_captures_to_sequence_pattern(
        self,
        pattern: cst.MatchSequence,
        captures: list[tuple[str, CapturePath, int]],
    ) -> cst.MatchSequence:
        elements = list(pattern.patterns)
        capture_map = {idx: var_name for var_name, _, idx in captures}
        max_index = max(capture_map)

        while len(elements) <= max_index:
            elements.append(
                cst.MatchSequenceElement(
                    value=cst.MatchAs(pattern=None, name=None),
                    comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" ")),
                )
            )

        for index, var_name in capture_map.items():
            elements[index] = elements[index].with_changes(
                value=cst.MatchAs(pattern=None, name=cst.Name(var_name))
            )

        star_index = next(
            (
                index
                for index, element in enumerate(elements)
                if isinstance(element.value, cst.MatchStar)
            ),
            None,
        )
        if star_index is not None:
            last_required_index = max_index
            for index, element in enumerate(elements[:star_index]):
                if not self._is_wildcard_sequence_element(element):
                    last_required_index = max(last_required_index, index)
            elements = [
                *elements[: last_required_index + 1],
                *elements[star_index:],
            ]

        return pattern.with_changes(patterns=elements)

    def _is_wildcard_sequence_element(self, element: cst.MatchSequenceElement) -> bool:
        return (
            isinstance(element.value, cst.MatchAs)
            and element.value.pattern is None
            and element.value.name is None
        )

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

            if not isinstance(kwd.pattern, (cst.MatchClass, cst.MatchOr)):
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

    def _prepend_aliases(
        self, body: cst.IndentedBlock, aliases: list[tuple[str, str]]
    ) -> cst.IndentedBlock:
        alias_statements = [
            cst.SimpleStatementLine(
                body=[
                    cst.Assign(
                        targets=[cst.AssignTarget(target=cst.Name(alias_name))],
                        value=cst.Name(source_name),
                    )
                ]
            )
            for alias_name, source_name in aliases
        ]

        if (
            len(body.body) == 1
            and isinstance(body.body[0], cst.SimpleStatementLine)
            and len(body.body[0].body) == 1
            and isinstance(body.body[0].body[0], cst.Pass)
        ):
            return body.with_changes(body=alias_statements)

        return body.with_changes(body=[*alias_statements, *body.body])
