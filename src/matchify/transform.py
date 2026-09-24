"""Plan independent conversions, then apply the selected replacements."""

from dataclasses import dataclass
from typing import NamedTuple, cast

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from .assumptions import AssumptionDiagnostic, Assumptions
from .compiler import IfChainCompiler
from .conversion_filter import (
    ConversionFilter,
    ConversionFilterDiagnostic,
    ConversionMetrics,
    with_generated_metrics,
)
from .lookup_tables import (
    compile_inline_lookup,
    compile_local_lookups,
    find_inline_lookup,
)


def _indent_snippet(code: str, indent: str) -> str:
    if not indent:
        return code
    return "".join(
        indent + line if line.strip() else line
        for line in code.splitlines(keepends=True)
    )


class ChainPreview(NamedTuple):
    line: int
    column: int
    before: str
    after: str
    extra_assumptions: frozenset[str]
    metrics: ConversionMetrics | None


@dataclass(frozen=True)
class ConversionCandidate:
    original: cst.BaseStatement
    replacement: cst.BaseStatement
    required_assumptions: Assumptions
    metrics: ConversionMetrics | None
    position: CodeRange


@dataclass
class ConversionPlan:
    """Candidates retain original node references for applying nested changes."""

    module: cst.Module
    source: str
    candidates: list[ConversionCandidate]

    def select(
        self,
        assumptions: Assumptions,
        convert_if: str | ConversionFilter | None = None,
        *,
        include_gated: bool = False,
        render_previews: bool = False,
    ) -> "SelectedConversions":
        conversion_filter = (
            ConversionFilter.parse(convert_if)
            if isinstance(convert_if, str)
            else convert_if
        )
        replacements: dict[cst.CSTNode, cst.CSTNode] = {}
        previews: list[ChainPreview] = []
        diagnostics: list[AssumptionDiagnostic] = []
        filter_diagnostics: list[ConversionFilterDiagnostic] = []
        source_lines = self.source.splitlines(keepends=True) if render_previews else []
        for candidate in self.candidates:
            missing = candidate.required_assumptions.names - assumptions.names
            position = candidate.position.start
            if missing:
                diagnostics.append(
                    AssumptionDiagnostic(position.line, position.column, missing)
                )
                if not include_gated:
                    continue
            if conversion_filter is not None and candidate.metrics is not None:
                try:
                    matches = conversion_filter.matches(candidate.metrics)
                except ArithmeticError:
                    if missing:
                        continue
                    raise
                if not matches:
                    if not missing:
                        filter_diagnostics.append(
                            ConversionFilterDiagnostic(position.line, position.column)
                        )
                    continue
            if not missing:
                replacements[candidate.original] = candidate.replacement
            if render_previews:
                previews.append(self._preview(candidate, missing, source_lines))
        return SelectedConversions(
            self.module, replacements, previews, diagnostics, filter_diagnostics
        )

    def _preview(
        self,
        candidate: ConversionCandidate,
        missing: frozenset[str],
        source_lines: list[str],
    ) -> ChainPreview:
        position = candidate.position.start
        indent = source_lines[position.line - 1][: position.column]
        return ChainPreview(
            position.line,
            position.column,
            _indent_snippet(
                self.module.code_for_node(
                    candidate.original.with_changes(leading_lines=())
                ),
                indent,
            ),
            _indent_snippet(
                self.module.code_for_node(
                    candidate.replacement.with_changes(leading_lines=())
                ),
                indent,
            ),
            missing,
            candidate.metrics,
        )


@dataclass
class SelectedConversions:
    module: cst.Module
    replacements: dict[cst.CSTNode, cst.CSTNode]
    previews: list[ChainPreview]
    diagnostics: list[AssumptionDiagnostic]
    filter_diagnostics: list[ConversionFilterDiagnostic]

    def apply(self) -> str:
        return self.module.visit(_ApplyConversions(self.replacements)).code


class _UpdatedChildren(cst.CSTTransformer):
    def __init__(self, updated: dict[cst.CSTNode, cst.CSTNode]) -> None:
        self.updated = updated

    def on_visit(self, node: cst.CSTNode) -> bool:
        return node not in self.updated

    def on_leave(
        self, original_node: cst.CSTNodeT, updated_node: cst.CSTNodeT
    ) -> cst.CSTNodeT:
        return cast(cst.CSTNodeT, self.updated.get(original_node, updated_node))


class _ApplyConversions(cst.CSTTransformer):
    def __init__(self, replacements: dict[cst.CSTNode, cst.CSTNode]) -> None:
        self.replacements = replacements
        self.updated: dict[cst.CSTNode, cst.CSTNode] = {}

    def on_leave(
        self, original_node: cst.CSTNodeT, updated_node: cst.CSTNodeT
    ) -> cst.CSTNodeT:
        replacement = self.replacements.get(original_node)
        if replacement is not None:
            # Reuse transformed descendants inside the independently compiled plan.
            updated_node = cast(
                cst.CSTNodeT, replacement.visit(_UpdatedChildren(self.updated))
            )
        self.updated[original_node] = updated_node
        return updated_node


class _PlanVisitor(cst.CSTVisitor):
    def __init__(
        self, wrapper: MetadataWrapper, ignore_types_pattern: str | None
    ) -> None:
        self.wrapper = wrapper
        self.compiler = IfChainCompiler(ignore_types_pattern=ignore_types_pattern)
        self.elif_nodes: set[cst.If] = set()
        self.candidates: list[ConversionCandidate] = []

    def _append(
        self,
        node: cst.BaseStatement,
        replacement: cst.BaseStatement,
        required: Assumptions,
        metrics: ConversionMetrics | None = None,
    ) -> None:
        # Resolve once, only when the module actually contains a candidate.
        position = self.wrapper.resolve(PositionProvider)[node]
        self.candidates.append(
            ConversionCandidate(node, replacement, required, metrics, position)
        )

    def visit_If(self, node: cst.If) -> bool:
        if isinstance(node.orelse, cst.If):
            self.elif_nodes.add(node.orelse)
        if node in self.elif_nodes:
            return True
        chain = self.compiler.extract_chain(node)
        if chain is not None:
            replacement = self.compiler.compile(chain, tuple(node.leading_lines))
            self._append(
                node,
                replacement,
                chain.required_assumptions,
                with_generated_metrics(chain.metrics, replacement),
            )
        return True

    def visit_SimpleStatementLine(self, node: cst.SimpleStatementLine) -> bool:
        candidate = find_inline_lookup(node)
        if candidate is not None:
            self._append(
                node,
                compile_inline_lookup(node, candidate),
                Assumptions.LOOKUP_EQUALITY,
            )
        return False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        if isinstance(node.body, cst.IndentedBlock):
            body, required = compile_local_lookups(node.body, enabled=True)
            if required:
                self._append(
                    node, node.with_changes(body=body), Assumptions.LOOKUP_EQUALITY
                )
        return True


def plan_conversions(
    source: str, ignore_types_pattern: str | None = None
) -> ConversionPlan:
    # Parser-created trees have unique node identities and need no deep copy.
    wrapper = MetadataWrapper(cst.parse_module(source), unsafe_skip_copy=True)
    visitor = _PlanVisitor(wrapper, ignore_types_pattern)
    wrapper.visit(visitor)
    return ConversionPlan(wrapper.module, source, visitor.candidates)


class IfToMatchTransformer(cst.CSTTransformer):
    """Compatibility adapter for callers visiting a parsed module directly."""

    def __init__(
        self,
        ignore_types_pattern: str | None = r".*_TYPES$",
        *,
        assumptions: Assumptions | None = None,
        convert_if: str | ConversionFilter | None = None,
    ) -> None:
        self.ignore_types_pattern = ignore_types_pattern
        self.assumptions = assumptions or Assumptions.from_names()
        self.convert_if = convert_if
        self.diagnostics: list[AssumptionDiagnostic] = []
        self.filter_diagnostics: list[ConversionFilterDiagnostic] = []

    def visit_Module(self, node: cst.Module) -> bool:
        return False

    def leave_Module(
        self, original_node: cst.Module, updated_node: cst.Module
    ) -> cst.Module:
        wrapper = MetadataWrapper(original_node)
        visitor = _PlanVisitor(wrapper, self.ignore_types_pattern)
        wrapper.visit(visitor)
        selected = ConversionPlan(
            wrapper.module, original_node.code, visitor.candidates
        ).select(self.assumptions, self.convert_if)
        self.diagnostics = selected.diagnostics
        self.filter_diagnostics = selected.filter_diagnostics
        return selected.module.visit(_ApplyConversions(selected.replacements))


def collect_chain_previews(
    source: str,
    *,
    ignore_types_pattern: str | None = None,
    assumptions: Assumptions | None = None,
    include_gated: bool = False,
    convert_if: str | ConversionFilter | None = None,
    filter_diagnostics: list[ConversionFilterDiagnostic] | None = None,
) -> list[ChainPreview]:
    selected = plan_conversions(source, ignore_types_pattern).select(
        assumptions or Assumptions.from_names(),
        convert_if,
        include_gated=include_gated,
        render_previews=True,
    )
    if filter_diagnostics is not None:
        filter_diagnostics.extend(selected.filter_diagnostics)
    return selected.previews


def transform_code(
    source: str,
    ignore_types_pattern: str | None = None,
    *,
    assumptions: Assumptions | None = None,
    diagnostics: list[AssumptionDiagnostic] | None = None,
    convert_if: str | ConversionFilter | None = None,
    filter_diagnostics: list[ConversionFilterDiagnostic] | None = None,
) -> str:
    """Apply the fixed candidates authorized by assumptions and the filter."""
    selected = plan_conversions(source, ignore_types_pattern).select(
        assumptions or Assumptions.from_names(), convert_if
    )
    if diagnostics is not None:
        diagnostics.extend(selected.diagnostics)
    if filter_diagnostics is not None:
        filter_diagnostics.extend(selected.filter_diagnostics)
    return selected.apply() if selected.replacements else source
