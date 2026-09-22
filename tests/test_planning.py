import pickle
import sys
from textwrap import dedent
from unittest.mock import patch

import libcst as cst
import pytest

from matchify import IfToMatchTransformer
from matchify.assumptions import Assumptions
from matchify.cli import main
from matchify.compiler import IfChainCompiler
from matchify.transform import collect_chain_previews, plan_conversions, transform_code


@pytest.mark.parametrize(
    ("condition", "other", "required"),
    [
        ("a.x == 1 and b.y == 2", "a.x == 3 and b.y == 4", {"pure-subjects"}),
        ("value.x == 1", "value.y == 2", {"use-object"}),
        ("value is Kind.FIRST", "value is Kind.SECOND", {"identity-equality"}),
        ("value in {1, 2}", "value == 3", {"hashable-subjects"}),
        (
            "isinstance(value, list) and len(value) == 1 and value[0] == 1",
            "value is None",
            {"list-sequence-pattern"},
        ),
        (
            "isinstance(value, (list, tuple)) and len(value) == 1 and value[0] == 1",
            "value is None",
            {"list-sequence-pattern", "tuple-sequence-pattern"},
        ),
    ],
)
def test_assumptions_gate_one_fixed_candidate(condition, other, required):
    source = f"if {condition}:\n    first()\nelif {other}:\n    second()\n"
    plan = plan_conversions(source)
    assert len(plan.candidates) == 1
    assert plan.candidates[0].required_assumptions.names == required

    safe = plan.select(Assumptions.safe(), include_gated=True, render_previews=True)
    enabled = plan.select(Assumptions.from_names(required), render_previews=True)
    risky = plan.select(Assumptions.risky(), render_previews=True)

    assert safe.apply() == source
    assert enabled.apply() == risky.apply() == safe.previews[0].after
    assert (
        safe.previews[0].metrics
        == enabled.previews[0].metrics
        == risky.previews[0].metrics
    )
    for missing in required:
        assert (
            plan.select(Assumptions.from_names(required - {missing})).apply() == source
        )
    assert (
        transform_code(
            transform_code(source), assumptions=Assumptions.from_names(required)
        )
        == enabled.apply()
    )


@pytest.mark.parametrize("assumptions", [None, Assumptions.USE_OBJECT])
def test_shared_short_circuited_subject_requires_pure_subjects(assumptions):
    source = dedent(
        """\
        a = c = 0
        if a == 1 and b == 2:
            result = "first"
        elif c == 3 and b == 4:
            result = "second"
        else:
            result = "other"
        """
    )
    diagnostics = []
    transformed = transform_code(
        source, assumptions=assumptions, diagnostics=diagnostics
    )
    original_namespace = {}
    transformed_namespace = {}
    exec(source, original_namespace)
    exec(transformed, transformed_namespace)

    assert transformed_namespace["result"] == original_namespace["result"] == "other"
    assert transformed == source
    assert diagnostics[0].assumptions == frozenset({"pure-subjects"})

    plan = plan_conversions(source)
    preview = plan.select(
        Assumptions.safe(), include_gated=True, render_previews=True
    ).previews[0]
    enabled = plan.select(Assumptions.PURE_SUBJECTS, render_previews=True)
    assert enabled.previews[0].after == preview.after
    assert "match b:" in enabled.apply()
    namespace = {"b": 2}
    exec(enabled.apply(), namespace)
    assert namespace["result"] == "other"


def test_planned_nested_conversions_keep_captures_aliases_and_independent_previews():
    source = dedent(
        """\
        if len(data) == 2 and data[0] == 1:
            item = data[1]
            alias = data[1]
            if item == 2:
                first(alias)
            elif item == 3:
                second(alias)
        elif data is None:
            other()
    """
    )
    plan = plan_conversions(source)
    selected = plan.select(Assumptions.safe(), render_previews=True)
    outer, inner = selected.previews
    assert "match data:" in outer.after
    assert "if item == 2:" in outer.after
    assert "match item:" in inner.after
    assert "case 1, item:" in selected.apply()
    assert "alias = item" in selected.apply()
    assert "match item:" in selected.apply()
    compile(selected.apply(), "<test>", "exec")

    child_only = plan.select(Assumptions.safe(), "captures == 0")
    assert "if len(data)" in child_only.apply()
    assert "match item:" in child_only.apply()


def test_lookup_plan_preserves_nested_if_and_inline_lookup_changes():
    source = dedent(
        """\
        def choose(key, value):
            table = {"a": 1, "b": 2}
            if value == 1:
                result = {"a": 3, "b": 4}[key]
            elif value == 2:
                result = 5
            return table[key]
    """
    )
    plan = plan_conversions(source)
    selected = plan.select(Assumptions.risky(), render_previews=True)
    transformed = selected.apply()
    assert transformed.count("match key:") == 2
    assert "match value:" in transformed
    assert "table =" not in transformed
    assert "if value == 1:" in selected.previews[0].after
    assert pickle.loads(pickle.dumps(selected)).apply() == transformed


def test_hidden_candidate_filter_error_does_not_discard_eligible_preview():
    source = dedent(
        """\
        if len(data) == 1 and data[0] == 1:
            first()
        elif len(data) == 1 and data[0] == 2:
            second()
        if value.x == 1:
            first()
        elif value.y == 2:
            second()
    """
    )
    previews = collect_chain_previews(
        source, include_gated=True, convert_if="patterns / sequence_patterns >= 1"
    )
    assert len(previews) == 1
    assert "match data:" in previews[0].after


def test_missing_parent_assumptions_do_not_block_children_or_later_conversion():
    source = dedent(
        """\
        if a == 1 and b == 2:
            if value == 1:
                first()
            elif value == 2:
                second()
        elif a == 3 and b == 4:
            other()
    """
    )
    safe = transform_code(source)
    assert "if a == 1 and b == 2:" in safe
    assert "match value:" in safe
    assert transform_code(safe, assumptions=Assumptions.risky()) == transform_code(
        source, assumptions=Assumptions.risky()
    )


def test_overlapping_inline_and_local_lookup_plans_prefer_inline():
    source = dedent(
        """\
        def choose(key):
            table = {"a": 1, "b": 2}
            return table[key] + {"a": 3, "b": 4}[key]
    """
    )
    plan = plan_conversions(source)
    assert len(plan.candidates) == 1
    selected = plan.select(Assumptions.risky(), render_previews=True)
    result = selected.apply()
    assert 'table = {"a": 1, "b": 2}' in result
    assert "return table[key] + 3" in result
    assert "return table[key] + 4" in result
    assert selected.previews[0].after in result


def test_assumptions_are_not_required_for_checks_left_in_guards():
    source = "if value in {1, 2} and value == 2:\n    first()\nelif value == 3:\n    second()\n"
    selected = plan_conversions(source).select(Assumptions.safe())
    assert not selected.diagnostics
    assert "case _ if value in {1, 2} and value == 2:" in selected.apply()


def test_show_write_applies_plans_returned_by_worker_processes(
    tmp_path, monkeypatch, capsys
):
    source = "if value == 1:\n    first()\nelif value == 2:\n    second()\n"
    paths = [tmp_path / "first.py", tmp_path / "second.py"]
    for path in paths:
        path.write_text(source)
    monkeypatch.setattr(
        sys, "argv", ["matchify", "--show", "--write", "--jobs", "2", str(tmp_path)]
    )
    main()
    assert all("match value:" in path.read_text() for path in paths)
    assert "2 converted, 0 unchanged, 0 errors" in capsys.readouterr().out


@pytest.mark.parametrize("interactive", [False, True])
def test_cli_previews_and_writes_one_compilation(
    tmp_path, monkeypatch, capsys, interactive
):
    source = "if value == 1:\n    first()\nelif value == 2:\n    second()\n"
    path = tmp_path / "example.py"
    path.write_text(source)
    argv = ["matchify", "--show", str(path)]
    if not interactive:
        argv.append("--write")
    else:
        argv.remove("--show")
        monkeypatch.setattr("matchify.cli.sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda _: "yes")
    monkeypatch.setattr(sys, "argv", argv)
    original_compile = IfChainCompiler.compile
    with patch("matchify.transform.cst.parse_module", wraps=cst.parse_module) as parse:
        with patch.object(
            IfChainCompiler, "compile", autospec=True, side_effect=original_compile
        ) as compile_chain:
            main()
    assert parse.call_count == compile_chain.call_count == 1
    assert "match value:" in path.read_text()
    assert "+match value:" in capsys.readouterr().out


def test_public_transformer_adapter_uses_fixed_candidates():
    source = "if a == 1 and b == 2:\n    pass\nelif a == 3 and b == 4:\n    pass\n"
    module = cst.parse_module(source)
    transformer = IfToMatchTransformer()
    assert module.visit(transformer).code == source
    assert transformer.diagnostics[0].assumptions == frozenset({"pure-subjects"})
    assert (
        "match (a, b):"
        in module.visit(IfToMatchTransformer(assumptions=Assumptions.risky())).code
    )
