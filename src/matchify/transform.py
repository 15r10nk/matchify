"""Top-level LibCST transformer orchestration."""

from __future__ import annotations

import libcst as cst
from libcst.metadata import PositionProvider

from .compiler import GenericIfChainCompiler


class IfToMatchTransformer(cst.CSTTransformer):
    """Generic guard-first if-chain transformer."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$"):
        super().__init__()
        self._elif_nodes: set[int] = set()
        self.ignore_types_pattern = ignore_types_pattern

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

        compiler = GenericIfChainCompiler(
            ignore_types_pattern=self.ignore_types_pattern
        )
        chain = compiler.extract_chain(original_node)
        if chain is None or not compiler.is_convertible(chain):
            return updated_node

        match_stmt = compiler.compile(chain, leading_lines=original_node.leading_lines)
        return self._transform_nested_cases(match_stmt)

    def _transform_nested_cases(self, match_stmt: cst.Match) -> cst.Match:
        """Run a fresh transformer over each case body so nested chains are handled."""
        new_cases = []
        for case in match_stmt.cases:
            new_body_stmts = []
            for stmt in case.body.body:
                temp_module = cst.Module(body=[stmt])
                wrapper = cst.MetadataWrapper(temp_module)
                transformer = IfToMatchTransformer(
                    ignore_types_pattern=self.ignore_types_pattern
                )
                transformed_module = wrapper.visit(transformer)
                new_body_stmts.extend(transformed_module.body)

            new_cases.append(
                case.with_changes(body=case.body.with_changes(body=new_body_stmts))
            )

        return match_stmt.with_changes(cases=new_cases)


def transform_code(source: str, ignore_types_pattern: str | None = None) -> str:
    """Transform Python source code by converting if/elif/else chains to match statements.

    Args:
        source: Python source code as a string
        ignore_types_pattern: Optional regex pattern for isinstance type variables to ignore

    Returns:
        Transformed source code as a string
    """
    module = cst.parse_module(source)

    # First pass: convert if/elif/else to match
    wrapper = cst.MetadataWrapper(module)
    transformed = wrapper.visit(
        IfToMatchTransformer(ignore_types_pattern=ignore_types_pattern)
    )

    return transformed.code
