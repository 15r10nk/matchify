"""Compile dictionary subscriptions embedded in simple statements."""

import ast
from dataclasses import dataclass

import libcst as cst
from libcst import matchers as m

from .patterns import build_value_pattern, is_value_pattern_expr


@dataclass(frozen=True)
class LookupCandidate:
    subscription: cst.Subscript
    table: cst.Dict
    subject: cst.BaseExpression


class _ReplaceNode(cst.CSTTransformer):
    def __init__(self, target: cst.CSTNode, replacement: cst.CSTNode) -> None:
        self.target = target
        self.replacement = replacement

    def on_leave(
        self, original_node: cst.CSTNode, updated_node: cst.CSTNode
    ) -> cst.CSTNode:
        return self.replacement if original_node is self.target else updated_node


def find_inline_lookup(statement: cst.SimpleStatementLine) -> LookupCandidate | None:
    subscriptions = tuple(m.findall(statement, m.Subscript(value=m.Dict())))
    if len(subscriptions) != 1:
        return None
    subscription = subscriptions[0]
    assert isinstance(subscription, cst.Subscript)
    assert isinstance(subscription.value, cst.Dict)
    if len(subscription.slice) != 1 or not isinstance(
        subscription.slice[0].slice, cst.Index
    ):
        return None
    candidate = LookupCandidate(
        subscription,
        subscription.value,
        subscription.slice[0].slice.value,
    )
    return candidate if lookup_entries(candidate.table) is not None else None


def lookup_entries(
    table: cst.Dict,
) -> tuple[tuple[cst.BaseExpression, cst.BaseExpression], ...] | None:
    entries: list[tuple[cst.BaseExpression, cst.BaseExpression]] = []
    literal_keys: list[object] = []
    for element in table.elements:
        if isinstance(element, cst.StarredDictElement):
            return None
        key = element.key
        value = element.value
        if key is None or not is_value_pattern_expr(key):
            return None
        try:
            literal_key = ast.literal_eval(cst.Module([]).code_for_node(key))
        except (ValueError, SyntaxError):
            return None
        if any(literal_key == previous for previous in literal_keys):
            return None
        literal_keys.append(literal_key)
        entries.append((key, value))
    return tuple(entries) if entries else None


def compile_inline_lookup(
    statement: cst.SimpleStatementLine,
    candidate: LookupCandidate,
) -> cst.Match:
    entries = lookup_entries(candidate.table)
    assert entries is not None, "Lookup candidates must contain valid entries"
    capture_name = _unused_capture_name(statement)
    cases: list[cst.MatchCase] = []
    for key, value in entries:
        body = statement.visit(_ReplaceNode(candidate.subscription, value))
        assert isinstance(body, cst.SimpleStatementLine)
        body = body.with_changes(leading_lines=())
        cases.append(
            cst.MatchCase(
                pattern=build_value_pattern(key),
                body=cst.IndentedBlock(body=(body,)),
            )
        )
    cases.append(
        cst.MatchCase(
            pattern=cst.MatchAs(name=cst.Name(capture_name)),
            body=cst.IndentedBlock(
                body=(
                    cst.SimpleStatementLine(
                        body=(
                            cst.Raise(
                                exc=cst.Call(
                                    func=cst.Name("KeyError"),
                                    args=(cst.Arg(cst.Name(capture_name)),),
                                )
                            ),
                        )
                    ),
                )
            ),
        )
    )
    return cst.Match(
        subject=candidate.subject,
        cases=tuple(cases),
        leading_lines=statement.leading_lines,
    )


def compile_local_lookups(
    body: cst.IndentedBlock,
    *,
    enabled: bool,
) -> tuple[cst.IndentedBlock, tuple[cst.SimpleStatementLine, ...]]:
    """Compile eligible function-local lookup variables.

    Returns the updated body and assignment nodes requiring the assumption.
    """
    statements = list(body.body)
    required: list[cst.SimpleStatementLine] = []
    for assignment_index, statement in tuple(enumerate(statements)):
        assignment = _local_dict_assignment(statement)
        if assignment is None:
            continue
        name, table = assignment
        uses = [
            node
            for candidate_statement in statements
            for node in m.findall(candidate_statement, m.Name(value=name))
        ]
        if len(uses) != 2:
            continue
        use = _local_lookup_use(statements, name, assignment_index)
        if use is None or lookup_entries(table) is None:
            continue
        use_index, use_statement, subscription = use
        if use_index <= assignment_index:
            continue
        required.append(statement)
        if not enabled:
            continue
        candidate = LookupCandidate(
            subscription, table, subscription.slice[0].slice.value
        )
        match_statement = compile_inline_lookup(use_statement, candidate)
        match_statement = match_statement.with_changes(
            leading_lines=(*statement.leading_lines, *match_statement.leading_lines)
        )
        statements[assignment_index] = cst.RemovalSentinel.REMOVE
        statements[use_index] = match_statement
    return body.with_changes(
        body=tuple(
            statement
            for statement in statements
            if statement is not cst.RemovalSentinel.REMOVE
        )
    ), tuple(required)


def _local_dict_assignment(
    statement: cst.BaseStatement,
) -> tuple[str, cst.Dict] | None:
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return None
    small = statement.body[0]
    if not isinstance(small, cst.Assign) or len(small.targets) != 1:
        return None
    target = small.targets[0].target
    if not isinstance(target, cst.Name) or not isinstance(small.value, cst.Dict):
        return None
    return target.value, small.value


def _local_lookup_use(
    statements: list[cst.BaseStatement], name: str, assignment_index: int
) -> tuple[int, cst.SimpleStatementLine, cst.Subscript] | None:
    matches: list[tuple[int, cst.SimpleStatementLine, cst.Subscript]] = []
    for index, statement in enumerate(statements):
        if index == assignment_index or not isinstance(
            statement, cst.SimpleStatementLine
        ):
            continue
        subscriptions = m.findall(statement, m.Subscript(value=m.Name(value=name)))
        for subscription in subscriptions:
            assert isinstance(subscription, cst.Subscript)
            if len(subscription.slice) == 1 and isinstance(
                subscription.slice[0].slice, cst.Index
            ):
                matches.append((index, statement, subscription))
    return matches[0] if len(matches) == 1 else None


def _unused_capture_name(statement: cst.CSTNode) -> str:
    names = {node.value for node in m.findall(statement, m.Name())}
    base = "_matchify_key"
    candidate = base
    suffix = 2
    while candidate in names:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate
