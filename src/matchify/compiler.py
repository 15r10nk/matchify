"""Normalize if/elif chains and compile them to match statements."""

from __future__ import annotations

from typing import NamedTuple

import libcst as cst
from libcst import matchers as m

from .capture_patterns import CapturePatternRewriter
from .facts import BranchFacts
from .patterns import extract_isinstance_classes
from .recognizers import SubjectRecognizer, normalize_branch
from .safety import is_safe_condition


class IfBranch(NamedTuple):
    """One if/elif branch in a convertible chain."""

    test: cst.BaseExpression
    body: cst.IndentedBlock
    leading_lines: tuple[cst.EmptyLine, ...]


class IfChain(NamedTuple):
    """A normalized if/elif/else chain, independent from LibCST navigation quirks."""

    subject: cst.BaseExpression
    branches: list[IfBranch]
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
        self.subject_recognizer = SubjectRecognizer(ignore_types_pattern)
        self.capture_patterns = CapturePatternRewriter()

    def extract_chain(self, node: cst.If) -> IfChain | None:
        subject = self.subject_recognizer.recognize(node.test)
        if subject is None or not isinstance(node.orelse, cst.If):
            return None

        branches: list[IfBranch] = []
        current: cst.If | None = node
        while current is not None:
            branch_subject = self.subject_recognizer.recognize(current.test)
            if branch_subject is None or not branch_subject.deep_equals(subject):
                return None

            leading_lines = () if current is node else current.leading_lines
            branches.append(IfBranch(current.test, current.body, leading_lines))

            if isinstance(current.orelse, cst.If):
                current = current.orelse
                continue
            if isinstance(current.orelse, cst.Else):
                return IfChain(
                    subject=subject,
                    branches=branches,
                    else_body=current.orelse.body,
                    else_leading_lines=current.orelse.leading_lines,
                )
            return IfChain(
                subject=subject,
                branches=branches,
                else_body=None,
                else_leading_lines=(),
            )

        # Defensive only: the loop returns as soon as the CST chain ends.
        return None  # pragma: no cover

    def is_convertible(self, chain: IfChain) -> bool:
        has_extractable_pattern = False

        for branch in chain.branches:
            if not is_safe_condition(branch.test, chain.subject):
                return False
            if self._has_problematic_isinstance(branch.test, chain.subject):
                return False

            facts = normalize_branch(
                branch.test, chain.subject, self.ignore_types_pattern
            )
            if facts.pattern is not None:
                has_extractable_pattern = True

        return has_extractable_pattern

    def compile(
        self, chain: IfChain, leading_lines: tuple[cst.EmptyLine, ...]
    ) -> cst.Match:
        cases = [
            self._compile_branch(branch, chain.subject) for branch in chain.branches
        ]

        if chain.else_body is not None:
            cases.append(
                cst.MatchCase(
                    pattern=cst.MatchAs(pattern=None, name=None),
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
        facts = normalize_branch(branch.test, subject, self.ignore_types_pattern)
        body = branch.body

        aliases = []
        if facts.pattern is not None:
            captures = self.capture_patterns._detect_multiple_captures(body, subject)
            if captures:
                captures, aliases = self.capture_patterns._normalize_duplicate_captures(
                    captures
                )
                capture_pattern = facts.pattern
                all_captures_applied = True
                for capture in captures:
                    next_pattern = capture_pattern.with_captures((capture,))
                    if next_pattern.render().deep_equals(capture_pattern.render()):
                        all_captures_applied = False
                        break
                    capture_pattern = next_pattern

                if all_captures_applied:
                    facts = BranchFacts(pattern=capture_pattern, guard=facts.guard)
                    body = self.capture_patterns._remove_statements(
                        body, len(captures) + len(aliases)
                    )
                    if aliases:
                        body = self.capture_patterns._prepend_aliases(body, aliases)

        pattern = (
            cst.MatchAs(pattern=None, name=None)
            if facts.pattern is None
            else facts.pattern.render()
        )
        guard = facts.guard

        kwargs = {
            "pattern": pattern,
            "guard": guard,
            "body": body,
            "leading_lines": branch.leading_lines,
        }
        if guard is not None:
            kwargs["whitespace_before_if"] = cst.SimpleWhitespace(" ")
            kwargs["whitespace_after_if"] = cst.SimpleWhitespace(" ")

        return cst.MatchCase(**kwargs)

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
