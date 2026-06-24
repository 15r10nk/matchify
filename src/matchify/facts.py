"""Normalized branch facts used as a bridge toward a recursive pattern IR."""

from __future__ import annotations

from dataclasses import dataclass

import libcst as cst


@dataclass(frozen=True)
class PatternTree:
    """Intermediate pattern node that can render to a LibCST match pattern.

    This currently wraps already-built LibCST patterns so the compiler can move
    to a fact-first interface before individual recognizers are migrated to real
    recursive nodes.
    """

    pattern: cst.MatchPattern

    def render(self) -> cst.MatchPattern:
        return self.pattern


@dataclass(frozen=True)
class BranchFacts:
    """Normalized facts for one branch condition."""

    condition: cst.BaseExpression
    subject: cst.BaseExpression
    pattern: PatternTree | None
    guard: cst.BaseExpression | None
