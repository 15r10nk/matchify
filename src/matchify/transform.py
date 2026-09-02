"""Top-level LibCST transformer orchestration."""

from itertools import combinations
from typing import NamedTuple

import libcst as cst
from libcst.metadata import CodePosition, CodeRange, MetadataWrapper, PositionProvider

from .assumptions import (
    ALL_RISKY_ASSUMPTIONS,
    LOOKUP_EQUALITY,
    PURE_SUBJECTS,
    AssumptionDiagnostic,
    Assumptions,
)
from .compiler import IfChainCompiler
from .lookup_tables import (
    compile_inline_lookup,
    compile_local_lookups,
    find_inline_lookup,
)


def _indent_snippet(code: str, indent: str) -> str:
    """Re-apply the original leading indent stripped by LibCST rendering."""
    if not indent:
        return code
    return "".join(
        indent + line if line.strip() else line
        for line in code.splitlines(keepends=True)
    )


class ChainPreview(NamedTuple):
    """One if/elif conversion that can be shown as a standalone diff."""

    line: int
    column: int
    before: str
    after: str
    extra_assumptions: frozenset[str]


def find_required_assumptions(
    node: cst.If,
    *,
    ignore_types_pattern: str | None,
    assumptions: Assumptions,
) -> frozenset[str]:
    """Return the smallest extra assumption set that makes *node* convertible."""
    missing = sorted(ALL_RISKY_ASSUMPTIONS - assumptions.names)
    for size in range(1, len(missing) + 1):
        for candidate in combinations(missing, size):
            extra = Assumptions.from_names((*assumptions.names, *candidate))
            compiler = IfChainCompiler(
                ignore_types_pattern=ignore_types_pattern,
                assumptions=extra,
            )
            if compiler.extract_chain(node) is not None:
                return frozenset(candidate)
    return frozenset()


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

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> cst.BaseStatement:
        candidate = find_inline_lookup(updated_node)
        if candidate is None:
            return updated_node
        if not self.assumptions.lookup_equality:
            self._record_diagnostic(original_node, frozenset({LOOKUP_EQUALITY}))
            return updated_node
        return compile_inline_lookup(updated_node, candidate)

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        if not isinstance(updated_node.body, cst.IndentedBlock):
            return updated_node
        body, required = compile_local_lookups(
            updated_node.body,
            enabled=self.assumptions.lookup_equality,
        )
        if required and not self.assumptions.lookup_equality:
            self._record_diagnostic(original_node, frozenset({LOOKUP_EQUALITY}))
        return updated_node.with_changes(body=body)

    def _record_missing_assumption_diagnostic(
        self, original_node: cst.If, updated_node: cst.If
    ) -> None:
        required_assumptions = self._find_required_assumptions(updated_node)
        if not required_assumptions:
            return

        self._record_diagnostic(original_node, required_assumptions)

    def _record_diagnostic(
        self, node: cst.CSTNode, assumptions: frozenset[str]
    ) -> None:
        position = self.get_metadata(
            PositionProvider,
            node,
            CodeRange(
                start=CodePosition(line=0, column=0),
                end=CodePosition(line=0, column=0),
            ),
        )
        self.diagnostics.append(
            AssumptionDiagnostic(
                line=position.start.line,
                column=position.start.column,
                assumptions=assumptions,
            )
        )

    def _find_required_assumptions(self, node: cst.If) -> frozenset[str]:
        return find_required_assumptions(
            node,
            ignore_types_pattern=self.ignore_types_pattern,
            assumptions=self.assumptions,
        )


class _ChainPreviewVisitor(cst.CSTVisitor):
    """Collect standalone before/after snippets for convertible if-chains."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        module: cst.Module,
        source: str,
        *,
        ignore_types_pattern: str | None,
        assumptions: Assumptions,
        include_gated: bool,
    ) -> None:
        super().__init__()
        self._module = module
        self._source_lines = source.splitlines(keepends=True)
        self._ignore_types_pattern = ignore_types_pattern
        self._assumptions = assumptions
        self._include_gated = include_gated
        self._elif_nodes: set[int] = set()
        self._compiler = IfChainCompiler(
            ignore_types_pattern=ignore_types_pattern,
            assumptions=assumptions,
        )
        self.previews: list[ChainPreview] = []

    def visit_If(self, node: cst.If) -> bool:
        if isinstance(node.orelse, cst.If):
            self._elif_nodes.add(id(node.orelse))
        if id(node) in self._elif_nodes:
            return True

        compiler = self._compiler
        extra_assumptions: frozenset[str] = frozenset()
        chain = compiler.extract_chain(node)
        if chain is None:
            if not self._include_gated:
                return True
            extra_assumptions = find_required_assumptions(
                node,
                ignore_types_pattern=self._ignore_types_pattern,
                assumptions=self._assumptions,
            )
            if not extra_assumptions:
                return True
            compiler = IfChainCompiler(
                ignore_types_pattern=self._ignore_types_pattern,
                assumptions=Assumptions.from_names(
                    (*self._assumptions.names, *extra_assumptions)
                ),
            )
            chain = compiler.extract_chain(node)
            if chain is None:  # pragma: no cover
                return True

        position = self.get_metadata(
            PositionProvider,
            node,
            CodeRange(
                start=CodePosition(line=0, column=0),
                end=CodePosition(line=0, column=0),
            ),
        )
        match_stmt = compiler.compile(chain, leading_lines=())
        indent = self._indent_for(position)
        self.previews.append(
            ChainPreview(
                line=position.start.line,
                column=position.start.column,
                before=_indent_snippet(
                    self._module.code_for_node(node.with_changes(leading_lines=())),
                    indent,
                ),
                after=_indent_snippet(
                    self._module.code_for_node(match_stmt),
                    indent,
                ),
                extra_assumptions=extra_assumptions,
            )
        )
        return True

    def _indent_for(self, position: CodeRange) -> str:
        if position.start.line <= 0 or position.start.line > len(self._source_lines):
            return ""
        line = self._source_lines[position.start.line - 1]
        return line[: position.start.column]


def collect_chain_previews(
    source: str,
    *,
    ignore_types_pattern: str | None = None,
    assumptions: Assumptions | None = None,
    include_gated: bool = False,
) -> list[ChainPreview]:
    """Return per-chain conversion snippets for preview diffs."""
    module = cst.parse_module(source)
    visitor = _ChainPreviewVisitor(
        module,
        source,
        ignore_types_pattern=ignore_types_pattern,
        assumptions=assumptions or Assumptions.from_names(),
        include_gated=include_gated,
    )
    MetadataWrapper(module).visit(visitor)
    return visitor.previews


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
