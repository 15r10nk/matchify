"""Top-level LibCST transformer orchestration."""

from itertools import combinations

import libcst as cst
from libcst.metadata import CodePosition, CodeRange, MetadataWrapper, PositionProvider

from .assumptions import (
    ALL_RISKY_ASSUMPTIONS,
    PURE_SUBJECTS,
    AssumptionDiagnostic,
    Assumptions,
)
from .compiler import IfChainCompiler


class IfToMatchTransformer(cst.CSTTransformer):
    """Generic guard-first if-chain transformer."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        ignore_types_pattern: str | None = r".*_TYPES$",
        *,
        assumptions: Assumptions | None = None,
        assume_pure_subjects: bool = False,
    ):
        super().__init__()
        resolved_assumptions = assumptions or Assumptions.from_names()
        if assume_pure_subjects:
            resolved_assumptions = Assumptions.from_names(
                (*resolved_assumptions.names, PURE_SUBJECTS)
            )
        self.assumptions = resolved_assumptions
        self.ignore_types_pattern = ignore_types_pattern
        self.diagnostics: list[AssumptionDiagnostic] = []
        self._elif_nodes: set[int] = set()
        self.compiler = IfChainCompiler(
            ignore_types_pattern=ignore_types_pattern,
            assumptions=resolved_assumptions,
        )

    def visit_If(self, node: cst.If) -> bool:
        """Track elif nodes so only the chain root performs replacement."""
        if isinstance(node.orelse, cst.If):
            self._elif_nodes.add(id(node.orelse))
        return True

    def leave_If(
        self, original_node: cst.If, updated_node: cst.If
    ) -> (
        cst.BaseStatement | cst.FlattenSentinel[cst.BaseStatement] | cst.RemovalSentinel
    ):
        if id(original_node) in self._elif_nodes:
            return updated_node

        chain = self.compiler.extract_chain(updated_node)
        if chain is None:
            self._record_missing_assumption_diagnostic(original_node, updated_node)
            return updated_node

        match_stmt = self.compiler.compile(
            chain, leading_lines=updated_node.leading_lines
        )
        return match_stmt

    def _record_missing_assumption_diagnostic(
        self, original_node: cst.If, updated_node: cst.If
    ) -> None:
        required_assumptions = self._find_required_assumptions(updated_node)
        if not required_assumptions:
            return

        position = self.get_metadata(
            PositionProvider,
            original_node,
            CodeRange(
                start=CodePosition(line=0, column=0),
                end=CodePosition(line=0, column=0),
            ),
        )
        self.diagnostics.append(
            AssumptionDiagnostic(
                line=position.start.line,
                column=position.start.column,
                assumptions=required_assumptions,
            )
        )

    def _find_required_assumptions(self, node: cst.If) -> frozenset[str]:
        missing = sorted(ALL_RISKY_ASSUMPTIONS - self.assumptions.names)
        for size in range(1, len(missing) + 1):
            for candidate in combinations(missing, size):
                assumptions = Assumptions.from_names(
                    (*self.assumptions.names, *candidate)
                )
                compiler = IfChainCompiler(
                    ignore_types_pattern=self.ignore_types_pattern,
                    assumptions=assumptions,
                )
                if compiler.extract_chain(node) is not None:
                    return frozenset(candidate)
        return frozenset()


def transform_code(
    source: str,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    assume_pure_subjects: bool = False,
    diagnostics: list[AssumptionDiagnostic] | None = None,
) -> str:
    """Transform Python source code by converting if/elif/else chains to match statements.

    Args:
        source: Python source code as a string
        ignore_types_pattern: Optional regex pattern for isinstance type variables to ignore
        assumptions: Enabled risky transformation assumptions
        assume_pure_subjects: Allow eager composite subjects from boolean conditions
        diagnostics: Optional list populated with skipped assumption-only conversions

    Returns:
        Transformed source code as a string
    """
    module = cst.parse_module(source)

    transformer = IfToMatchTransformer(
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions,
        assume_pure_subjects=assume_pure_subjects,
    )
    transformed = MetadataWrapper(module).visit(transformer)
    if diagnostics is not None:
        diagnostics.extend(transformer.diagnostics)

    return transformed.code
