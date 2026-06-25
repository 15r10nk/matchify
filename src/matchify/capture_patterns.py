"""Capture assignment helpers for compiled match cases."""

from __future__ import annotations

import libcst as cst

from .facts import CaptureFact
from .subject_path import SubjectPath, extract_integer_subscript_index


def detect_multiple_captures(
    body: cst.IndentedBlock, subject: cst.BaseExpression
) -> list[CaptureFact]:
    captures = []

    for stmt in body.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            break
        if len(stmt.body) != 1 or not isinstance(stmt.body[0], cst.Assign):
            break

        assign = stmt.body[0]
        if len(assign.targets) != 1:
            break

        target = assign.targets[0].target
        if not isinstance(target, cst.Name):
            break

        if not isinstance(assign.value, cst.Subscript):
            break

        path = SubjectPath.from_expression(assign.value.value, subject)
        if path is None:
            break
        index = extract_integer_subscript_index(assign.value)
        if index is None:
            break

        captures.append(CaptureFact(name=target.value, path=path, index=index))

    return captures


def normalize_duplicate_captures(
    captures: list[CaptureFact],
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


def remove_statements(body: cst.IndentedBlock, count: int) -> cst.IndentedBlock:
    if len(body.body) <= count:
        pass_stmt = cst.SimpleStatementLine(body=[cst.Pass()])
        return body.with_changes(body=[pass_stmt])
    return body.with_changes(body=body.body[count:])


def prepend_aliases(
    body: cst.IndentedBlock, aliases: list[tuple[str, str]]
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
