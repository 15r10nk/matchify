"""Normalize if/elif chains and compile them to match statements."""

from __future__ import annotations

from typing import NamedTuple

import libcst as cst
from libcst import matchers as m

from .patterns import is_ignored_type_expr
from .recognizers import PatternRecognitionEngine
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
        self.recognition = PatternRecognitionEngine(ignore_types_pattern)

    def extract_chain(self, node: cst.If) -> IfChain | None:
        subject = self.recognition.recognize_subject(node.test)
        if subject is None or not isinstance(node.orelse, cst.If):
            return None

        branches: list[IfBranch] = []
        current: cst.If | None = node
        while current is not None:
            branch_subject = self.recognition.recognize_subject(current.test)
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

        return None

    def is_convertible(self, chain: IfChain) -> bool:
        has_extractable_pattern = False

        for branch in chain.branches:
            if not is_safe_condition(
                branch.test, chain.subject, self.ignore_types_pattern
            ):
                return False
            if self._has_problematic_isinstance(branch.test, chain.subject):
                return False

            result = self.recognition.recognize_branch(branch.test, chain.subject)
            if result.pattern is not None:
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
        result = self.recognition.recognize_branch(branch.test, subject)
        pattern = result.pattern
        guard = result.guard
        if pattern is None:
            pattern = cst.MatchAs(pattern=None, name=None)

        kwargs = {
            "pattern": pattern,
            "guard": guard,
            "body": branch.body,
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

            class_arg = call.args[1].value
            if is_ignored_type_expr(class_arg, self.ignore_types_pattern):
                return True
            if isinstance(class_arg, cst.Tuple):
                if not class_arg.elements:
                    return True
                for elem in class_arg.elements:
                    if isinstance(elem, cst.StarredElement):
                        return True
                    if isinstance(elem, cst.Element) and is_ignored_type_expr(
                        elem.value, self.ignore_types_pattern
                    ):
                        return True

        return False
