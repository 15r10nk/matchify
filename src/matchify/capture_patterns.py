"""Capture assignment helpers for compiled match cases."""

from __future__ import annotations

import libcst as cst

from .facts import CaptureFact
from .subject_path import SubjectPath


class CapturePatternRewriter:
    """Detect leading capture assignments and rewrite the remaining case body.

    Pattern construction happens in ``PatternTree``. This helper only derives
    explicit ``CaptureFact`` values from body assignments and removes the body
    statements after the compiler proves they were rendered into the pattern.
    """

    def _detect_multiple_captures(
        self, body: cst.IndentedBlock, subject: cst.BaseExpression
    ) -> list[CaptureFact]:
        """Detect multiple consecutive capture assignments at the start of body.

        Returns:
            List of capture facts, one for each capture assignment.
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
        self, captures: list[CaptureFact]
    ) -> tuple[list[CaptureFact], list[tuple[str, str]]]:
        """Keep one pattern capture per source index and alias later duplicates."""
        seen: dict[tuple[SubjectPath, int], str] = {}
        unique_captures = []
        aliases = []

        for capture in captures:
            key = (capture.path, capture.index)
            if key in seen:
                aliases.append((capture.name, seen[key]))
                continue
            seen[key] = capture.name
            unique_captures.append(capture)

        return unique_captures, aliases

    def _detect_capture_assignment(
        self, assign: cst.Assign, subject: cst.BaseExpression
    ) -> CaptureFact | None:
        """Detect if assignment is like: var = subject.attr[index].

        Returns:
            Capture fact or None if not matching pattern.
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
        # Check index is an integer literal
        if not isinstance(subscript.slice[0].slice, cst.Index):
            return None

        index_node = subscript.slice[0].slice.value
        if not isinstance(index_node, cst.Integer):
            return None

        index = int(index_node.value)

        return CaptureFact(name=var_name, path=path, index=index)

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
