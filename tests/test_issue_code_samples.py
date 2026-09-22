from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import test_code_samples as code_samples  # noqa: E402

import find_pattern_coverage_issue  # noqa: E402
import find_random_trace_issue  # noqa: E402
from code_sample_format import parse_sample  # noqa: E402
from code_sample_runtime import Trace  # noqa: E402


@pytest.mark.parametrize(
    "finder", [find_random_trace_issue, find_pattern_coverage_issue]
)
def test_conversion_error_is_recorded_and_saved(finder, monkeypatch, tmp_path):
    def fail_conversion(*args, **kwargs):
        raise RuntimeError("conversion failed")

    monkeypatch.setattr(finder, "transform_code", fail_conversion)
    if finder is find_random_trace_issue:
        source = "pass\n"
        issue = finder.check_source(source)
    else:
        program = finder.Program(
            classes=(),
            subject="value",
            cases=(finder.Case(finder.LiteralPattern("1"), "one"),),
            default_body=None,
            sample_values=("2",),
        )
        source = program.render_if_code(finder.IfStyle.CANONICAL, 0)
        issue = finder.check_program(program, finder.IfStyle.CANONICAL, seed=0)

    assert issue.kind == "convert-error"
    assert issue.original == source
    assert issue.converted == source
    assert not issue.changed
    assert issue.error == "RuntimeError('conversion failed')"
    sample_path = finder.save_issue(issue, tmp_path)
    assert parse_sample(sample_path.read_text()).before == source + "\n"


def test_random_trace_finder_saves_flat_code_sample(tmp_path):
    source = 'print("before")\n'
    issue = find_random_trace_issue.Issue(
        kind="trace-mismatch",
        seed=12,
        index=3,
        original=source,
        converted='print("after")\n',
        expected_trace=Trace("before\n", "", None, None),
        actual_trace=Trace("after\n", "", None, None),
        changed=True,
    )

    sample_path = find_random_trace_issue.save_issue(issue, tmp_path)

    assert sample_path.parent == tmp_path
    assert sample_path.suffix == ".py"
    assert sample_path.read_text(encoding="utf-8") == (
        "# generated-kind: trace-mismatch\n"
        "# seed: 12\n"
        "# case: 3\n"
        "# before:\n"
        'print("before")\n\n'
        "# after:\n"
        'print("after")\n\n'
        "# assume:\n\n"
        "# trace:\n"
        "# before\n"
    )


def test_exception_only_mismatch_can_be_saved(monkeypatch, tmp_path):
    source = "raise ValueError('details')\n"
    monkeypatch.setattr(find_random_trace_issue, "transform_code", lambda _: "pass\n")

    issue = find_random_trace_issue.check_source(source)

    assert issue.kind == "trace-mismatch"
    assert issue.expected_trace == Trace("", "", ValueError, ("details",))
    assert issue.actual_trace == Trace("", "", None, None)
    sample_path = find_random_trace_issue.save_issue(issue, tmp_path)
    content = sample_path.read_text()
    assert parse_sample(content).before == source + "\n"
    assert "# after:\npass\n" in content
    assert content.endswith(
        "# trace:\n# exception: ValueError\n# exception-args: ('details',)\n"
    )


def test_pattern_coverage_finder_saves_flat_code_sample(tmp_path):
    source = 'print("branch")\n'
    issue = find_pattern_coverage_issue.Issue(
        kind="not-converted",
        seed=14,
        index=5,
        style="mixed",
        original=source,
        converted=source,
        match_reference=source,
        expected_trace=Trace("branch\n", "", None, None),
        actual_trace=Trace("branch\n", "", None, None),
        changed=False,
    )

    sample_path = find_pattern_coverage_issue.save_issue(issue, tmp_path)

    assert sample_path.parent == tmp_path
    assert sample_path.suffix == ".py"
    content = sample_path.read_text(encoding="utf-8")
    sample = parse_sample(content)
    assert sample.before == source + "\n"
    assert not sample.assumptions.names
    assert sample.ignore_types_pattern is None
    assert sample.reference == source
    assert "# generated-kind: not-converted\n" in content
    assert "# style: mixed\n" in content
    assert f"# before:\n{source}\n# after:\n{source}" in content
    assert content.endswith("# trace:\n# branch\n")
    code_samples.test_code_sample(sample_path)


def test_generator_bug_preserves_reference_and_fails_sample_check(
    monkeypatch, tmp_path
):
    finder = find_pattern_coverage_issue
    program = finder.Program(
        classes=(),
        subject="value",
        cases=(finder.Case(finder.LiteralPattern("1"), "one"),),
        default_body=None,
        sample_values=("1",),
    )
    render_if_code = finder.Program.render_if_code

    def broken_render_if_code(self, style, seed):
        return render_if_code(self, style, seed).replace(
            "print('one')", "print('wrong')"
        )

    monkeypatch.setattr(finder.Program, "render_if_code", broken_render_if_code)
    issue = finder.check_program(program, finder.IfStyle.CANONICAL, seed=0)

    assert issue.kind == "generator-bug"
    sample_path = finder.save_issue(issue, tmp_path)
    content = sample_path.read_text(encoding="utf-8")
    assert parse_sample(content).reference == issue.match_reference
    assert content.endswith("# trace:\n# one\n")
    with pytest.raises(AssertionError, match="reference"):
        code_samples.test_code_sample(sample_path)

    # Correcting the faulty renderer output should satisfy the preserved oracle.
    sample_path.write_text(
        content.replace("print('wrong')", "print('one')"),
        encoding="utf-8",
        newline="\n",
    )
    code_samples.test_code_sample(sample_path)


def test_issue_finders_default_to_code_samples_directory():
    expected = Path("tests/code_samples")

    assert find_random_trace_issue.SAMPLES_DIR == expected
    assert find_pattern_coverage_issue.SAMPLES_DIR == expected
