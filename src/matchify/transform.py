"""Top-level LibCST transformer orchestration."""

import libcst as cst

from .compiler import GenericIfChainCompiler


class IfToMatchTransformer(cst.CSTTransformer):
    """Generic guard-first if-chain transformer."""

    def __init__(self, ignore_types_pattern: str | None = r".*_TYPES$"):
        super().__init__()
        self._elif_nodes: set[int] = set()
        self.compiler = GenericIfChainCompiler(
            ignore_types_pattern=ignore_types_pattern
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
        if chain is None or not self.compiler.is_convertible(chain):
            return updated_node

        match_stmt = self.compiler.compile(
            chain, leading_lines=updated_node.leading_lines
        )
        return match_stmt


def transform_code(source: str, ignore_types_pattern: str | None = None) -> str:
    """Transform Python source code by converting if/elif/else chains to match statements.

    Args:
        source: Python source code as a string
        ignore_types_pattern: Optional regex pattern for isinstance type variables to ignore

    Returns:
        Transformed source code as a string
    """
    module = cst.parse_module(source)

    transformed = module.visit(
        IfToMatchTransformer(ignore_types_pattern=ignore_types_pattern)
    )

    return transformed.code
