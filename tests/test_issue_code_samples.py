from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import find_pattern_coverage_issue  # noqa: E402
import find_random_trace_issue  # noqa: E402
from code_sample_format import parse_sample  # noqa: E402
from code_sample_runtime import Trace  # noqa: E402


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
    assert "# generated-kind: not-converted\n" in content
    assert "# style: mixed\n" in content
    assert f"# before:\n{source}\n# after:\n{source}" in content
    assert content.endswith("# trace:\n# branch\n")


def test_issue_finders_default_to_code_samples_directory():
    expected = Path("tests/code_samples")

    assert find_random_trace_issue.SAMPLES_DIR == expected
    assert find_pattern_coverage_issue.SAMPLES_DIR == expected
