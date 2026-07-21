"""Normalize if/elif chains and compile them to match statements."""

from typing import NamedTuple

import libcst as cst

from .access_path import MatchSubjectPlan
from .capture_patterns import (
    detect_captures,
    normalize_duplicate_captures,
    prepend_aliases,
    remove_statements,
)
from .conditions import (
    BoolExpr,
    parse_condition,
    select_assumed_pure_subject_paths,
    select_subject_paths,
)
from .facts import BranchFacts
from .pattern_builder import normalize_condition
from .patterns import build_wildcard_pattern
from .safety import is_safe_condition


class IfBranch(NamedTuple):
    """One if/elif branch in a convertible chain."""

    body: cst.IndentedBlock
    leading_lines: tuple[cst.EmptyLine, ...]
    facts: BranchFacts


class IfChain(NamedTuple):
    """A normalized if/elif/else chain, independent from LibCST navigation quirks."""

    subject: MatchSubjectPlan
    branches: tuple[IfBranch, ...]
    else_body: cst.IndentedBlock | None
    else_leading_lines: tuple[cst.EmptyLine, ...]


class ParsedBranch(NamedTuple):
    """One branch before its access paths are bound to a match subject."""

    test: cst.BaseExpression
    condition: BoolExpr
    body: cst.IndentedBlock
    leading_lines: tuple[cst.EmptyLine, ...]


class IfChainCompiler:
    """Analyze an if-chain once, then compile it to a match statement.

    The compiler is deliberately guard-first:
    every branch starts as `case _ if <original condition>`, and optimizers may
    move proven-safe pieces into the pattern. That makes unsupported constructs
    fail closed instead of silently dropping conditions.
    """

    def __init__(
        self,
        ignore_types_pattern: str | None = r".*_TYPES$",
        *,
        assume_pure_subjects: bool = False,
    ) -> None:
        self.ignore_types_pattern = ignore_types_pattern
        self.assume_pure_subjects = assume_pure_subjects

    def extract_chain(self, node: cst.If) -> IfChain | None:
        if not isinstance(node.orelse, cst.If):
            return None

        parsed_branches: list[ParsedBranch] = []
        current = node
        while True:
            leading_lines = () if current is node else current.leading_lines
            parsed_branches.append(
                ParsedBranch(
                    current.test,
                    parse_condition(current.test, self.ignore_types_pattern),
                    current.body,
                    leading_lines,
                )
            )

            if isinstance(current.orelse, cst.If):
                current = current.orelse
                continue
            if isinstance(current.orelse, cst.Else):
                else_body = current.orelse.body
                else_leading_lines = current.orelse.leading_lines
            else:
                else_body = None
                else_leading_lines = ()
            break

        subject = self._select_chain_subject(parsed_branches)
        if subject is None:
            return None

        branches: list[IfBranch] = []
        for branch in parsed_branches:
            if not is_safe_condition(
                branch.test,
                subject,
                ignore_types_pattern=self.ignore_types_pattern,
            ):
                return None
            branches.append(
                IfBranch(
                    branch.body,
                    branch.leading_lines,
                    normalize_condition(
                        branch.condition,
                        subject,
                        allow_object_anchors=self.assume_pure_subjects,
                    ),
                )
            )

        if not any(branch.facts.pattern is not None for branch in branches):
            return None
        return IfChain(
            subject=subject,
            branches=tuple(branches),
            else_body=else_body,
            else_leading_lines=else_leading_lines,
        )

    def _select_chain_subject(
        self, branches: list[ParsedBranch]
    ) -> MatchSubjectPlan | None:
        """Build a subject from the common prefix of all branch candidates."""
        if self.assume_pure_subjects:
            candidates = tuple(
                select_assumed_pure_subject_paths(branch.condition)
                for branch in branches
            )
            if any(paths is None for paths in candidates):
                return None
            return MatchSubjectPlan.from_shared_candidates(
                tuple(paths for paths in candidates if paths is not None)
            )

        candidates = tuple(
            select_subject_paths(branch.condition) for branch in branches
        )
        if any(candidate is None for candidate in candidates):
            return None
        return MatchSubjectPlan.from_aligned_candidates(
            tuple(candidate for candidate in candidates if candidate is not None)
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
            subject=chain.subject.to_expression(),
            cases=cases,
            leading_lines=leading_lines,
        )

    def _compile_branch(
        self, branch: IfBranch, subject: MatchSubjectPlan
    ) -> cst.MatchCase:
        facts = branch.facts
        body = branch.body

        if facts.pattern is not None:
            captures = detect_captures(body, subject)
            if captures:
                captures, aliases = normalize_duplicate_captures(captures)
                capture_pattern = facts.pattern
                for capture in captures:
                    next_pattern = capture_pattern.with_capture(capture)
                    if next_pattern is None:
                        break
                    capture_pattern = next_pattern
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

        return cst.MatchCase(
            pattern=pattern,
            guard=guard,
            body=body,
            leading_lines=branch.leading_lines,
            whitespace_before_if=(
                cst.SimpleWhitespace("") if guard is None else cst.SimpleWhitespace(" ")
            ),
            whitespace_after_if=(
                cst.SimpleWhitespace("") if guard is None else cst.SimpleWhitespace(" ")
            ),
        )
