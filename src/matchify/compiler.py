"""Normalize if/elif chains and compile them to match statements."""

from typing import NamedTuple

import libcst as cst
from libcst import matchers as m

from .capture_patterns import (
    detect_multiple_captures,
    normalize_duplicate_captures,
    prepend_aliases,
    remove_statements,
)
from .conditions import infer_subject, parse_condition
from .facts import BranchFacts
from .patterns import build_wildcard_pattern, extract_isinstance_classes
from .recognizers import normalize_branch
from .safety import is_safe_condition


class IfBranch(NamedTuple):
    """One if/elif branch in a convertible chain."""

    body: cst.IndentedBlock
    leading_lines: tuple[cst.EmptyLine, ...]
    facts: BranchFacts


class IfChain(NamedTuple):
    """A normalized if/elif/else chain, independent from LibCST navigation quirks."""

    subject: cst.BaseExpression
    branches: tuple[IfBranch, ...]
    else_body: cst.IndentedBlock | None
    else_leading_lines: tuple[cst.EmptyLine, ...]


class GenericIfChainCompiler:
    """Analyze an if-chain once, then compile it to a match statement.

    The compiler is deliberately guard-first:
    every branch starts as `case _ if <original condition>`, and optimizers may
    move proven-safe pieces into the pattern. That makes unsupported constructs
    fail closed instead of silently dropping conditions.
    """

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$") -> None:
        self.ignore_types_pattern = ignore_types_pattern

    def extract_chain(self, node: cst.If) -> IfChain | None:
        first_condition = parse_condition(node.test, self.ignore_types_pattern)
        subject = infer_subject(first_condition)
        if subject is None or not isinstance(node.orelse, cst.If):
            return None

        branches: list[IfBranch] = []
        current = node
        condition = first_condition
        while True:
            branch_subject = infer_subject(condition)
            if branch_subject is None or not branch_subject.deep_equals(subject):
                return None
            if not is_safe_condition(current.test, subject):
                return None
            if self._has_problematic_isinstance(current.test, subject):
                return None

            facts = normalize_branch(condition, subject)

            leading_lines = () if current is node else current.leading_lines
            branches.append(IfBranch(current.body, leading_lines, facts))

            if isinstance(current.orelse, cst.If):
                current = current.orelse
                condition = parse_condition(current.test, self.ignore_types_pattern)
                continue
            if isinstance(current.orelse, cst.Else):
                else_body = current.orelse.body
                else_leading_lines = current.orelse.leading_lines
            else:
                else_body = None
                else_leading_lines = ()

            if not any(branch.facts.pattern is not None for branch in branches):
                return None
            return IfChain(
                subject=subject,
                branches=tuple(branches),
                else_body=else_body,
                else_leading_lines=else_leading_lines,
            )

    def compile(
        self, chain: IfChain, leading_lines: tuple[cst.EmptyLine, ...]
    ) -> cst.Match:
        cases = [
            self._compile_branch(branch, chain.subject) for branch in chain.branches
        ]

        if chain.else_body is not None:
            cases.append(
                cst.MatchCase(
                    pattern=build_wildcard_pattern(),
                    body=chain.else_body,
                    leading_lines=chain.else_leading_lines,
                )
            )

        return cst.Match(
            subject=chain.subject, cases=cases, leading_lines=leading_lines
        )

    def _compile_branch(
        self, branch: IfBranch, subject: cst.BaseExpression
    ) -> cst.MatchCase:
        facts = branch.facts
        body = branch.body

        if facts.pattern is not None:
            captures = detect_multiple_captures(body, subject)
            if captures:
                captures, aliases = normalize_duplicate_captures(captures)
                capture_pattern = facts.pattern
                rendered_pattern = capture_pattern.render()
                for capture in captures:
                    next_pattern = capture_pattern.with_captures((capture,))
                    next_rendered_pattern = next_pattern.render()
                    if next_rendered_pattern.deep_equals(rendered_pattern):
                        break
                    capture_pattern = next_pattern
                    rendered_pattern = next_rendered_pattern
                else:
                    facts = BranchFacts(pattern=capture_pattern, guard=facts.guard)
                    body = remove_statements(body, len(captures) + len(aliases))
                    if aliases:
                        body = prepend_aliases(body, aliases)

        pattern = (
            build_wildcard_pattern()
            if facts.pattern is None
            else facts.pattern.render()
        )
        guard = facts.guard

        if guard is None:
            return cst.MatchCase(
                pattern=pattern,
                guard=None,
                body=body,
                leading_lines=branch.leading_lines,
            )

        return cst.MatchCase(
            pattern=pattern,
            guard=guard,
            body=body,
            leading_lines=branch.leading_lines,
            whitespace_before_if=cst.SimpleWhitespace(" "),
            whitespace_after_if=cst.SimpleWhitespace(" "),
        )

    def _has_problematic_isinstance(
        self, test: cst.BaseExpression, subject: cst.BaseExpression
    ) -> bool:
        for call in m.findall(test, m.Call(func=m.Name(value="isinstance"))):
            if len(call.args) < 2:
                return True
            if not call.args[0].value.deep_equals(subject):
                continue

            if (
                extract_isinstance_classes(
                    call.args[1].value, self.ignore_types_pattern
                )
                is None
            ):
                return True

        return False
