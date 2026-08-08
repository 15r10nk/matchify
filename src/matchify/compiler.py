"""Normalize if/elif chains and compile them to match statements."""

from collections.abc import Sequence
from typing import NamedTuple

import libcst as cst

from .access_path import MatchSubjectPlan
from .assumptions import Assumptions
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

    @property
    def is_wildcard_case(self) -> bool:
        """Whether this branch compiles to `case _`."""
        return self.facts.pattern is None


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
        assumptions: Assumptions | None = None,
    ) -> None:
        self.ignore_types_pattern = ignore_types_pattern
        self.assumptions = assumptions or Assumptions.from_names()

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
                    parse_condition(
                        current.test,
                        self.ignore_types_pattern,
                        assumptions=self.assumptions,
                    ),
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

        branches = self._analyze_branches(parsed_branches, subject)
        if branches is None:
            return None

        if not any(not branch.is_wildcard_case for branch in branches):
            return None
        wildcard_case_count = sum(branch.is_wildcard_case for branch in branches)
        if wildcard_case_count + int(else_body is not None) > 1:
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
        candidates = tuple(
            select_assumed_pure_subject_paths(branch.condition) for branch in branches
        )
        if any(paths is None for paths in candidates):
            return None
        concrete_candidates = tuple(paths for paths in candidates if paths is not None)
        if self.assumptions.assume_pure_subjects:
            return MatchSubjectPlan.from_majority_candidates(concrete_candidates)

        if self.assumptions.use_object:
            subject = MatchSubjectPlan.from_shared_candidates(concrete_candidates)
            if subject is not None and not subject.is_composite:
                return subject

        return MatchSubjectPlan.from_aligned_candidates(
            tuple((paths[0],) for paths in concrete_candidates)
        )

    def _analyze_branches(
        self, branches: Sequence[ParsedBranch], subject: MatchSubjectPlan
    ) -> tuple[IfBranch, ...] | None:
        analyzed: list[IfBranch] = []
        for branch in branches:
            analyzed_branch = self._analyze_branch(branch, subject)
            if analyzed_branch is None:
                return None
            analyzed.append(analyzed_branch)
        return tuple(analyzed)

    def _analyze_branch(
        self, branch: ParsedBranch, subject: MatchSubjectPlan
    ) -> IfBranch | None:
        if not is_safe_condition(
            branch.test,
            subject,
            ignore_types_pattern=self.ignore_types_pattern,
            assumptions=self.assumptions,
        ):
            return None
        facts = normalize_condition(
            branch.condition,
            subject,
            assumptions=self.assumptions,
            allow_object_anchors=self.assumptions.use_object,
        )
        return IfBranch(branch.body, branch.leading_lines, facts)

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
            if branch.is_wildcard_case
            else facts.pattern.render()
        )
        guard = parenthesize_multiline_guard(facts.guard)

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


def parenthesize_multiline_guard(
    guard: cst.BaseExpression | None,
) -> cst.BaseExpression | None:
    if guard is None:
        return None
    if "\n" not in cst.Module([]).code_for_node(guard):
        return guard
    return guard.with_changes(
        lpar=(cst.LeftParen(), *guard.lpar),
        rpar=(*guard.rpar, cst.RightParen()),
    )
