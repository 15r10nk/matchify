import libcst as cst

from matchify.recognizers import PatternRecognitionEngine


def normalize(condition_code: str, subject_code: str):
    engine = PatternRecognitionEngine()
    condition = cst.parse_expression(condition_code)
    subject = cst.parse_expression(subject_code)
    return engine.normalize_branch(condition, subject)


def test_normalize_branch_wraps_recognized_pattern():
    facts = normalize("value == 1", "value")

    assert facts.pattern is not None
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1"
    assert facts.guard is None


def test_normalize_branch_preserves_unrecognized_condition_as_guard():
    facts = normalize("value > 1", "value")

    assert facts.pattern is None
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == "value > 1"
