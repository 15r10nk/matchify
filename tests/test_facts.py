import libcst as cst

from matchify.facts import ClassFact, ValueFact
from matchify.recognizers import PatternRecognitionEngine


def normalize(condition_code: str, subject_code: str):
    engine = PatternRecognitionEngine()
    condition = cst.parse_expression(condition_code)
    subject = cst.parse_expression(subject_code)
    return engine.normalize_branch(condition, subject)


def test_normalize_branch_wraps_recognized_pattern():
    facts = normalize("value == 1", "value")

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ValueFact)
    assert facts.facts[0].path.is_subject
    assert cst.Module([]).code_for_node(facts.facts[0].value) == "1"
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1"
    assert facts.guard is None


def test_normalize_branch_preserves_unrecognized_condition_as_guard():
    facts = normalize("value > 1", "value")

    assert facts.pattern is None
    assert facts.facts == ()
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == "value > 1"


def test_normalize_branch_builds_singleton_value_fact():
    facts = normalize("value is None", "value")

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ValueFact)
    assert facts.facts[0].path.is_subject
    assert cst.Module([]).code_for_node(facts.facts[0].value) == "None"
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "None"


def test_normalize_branch_builds_class_fact():
    facts = normalize("isinstance(value, Point)", "value")

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ClassFact)
    assert facts.facts[0].path.is_subject
    assert [cst.Module([]).code_for_node(cls) for cls in facts.facts[0].classes] == [
        "Point"
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point()"


def test_normalize_branch_builds_class_union_fact():
    facts = normalize("isinstance(value, (Point, Token))", "value")

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ClassFact)
    assert facts.facts[0].path.is_subject
    assert [cst.Module([]).code_for_node(cls) for cls in facts.facts[0].classes] == [
        "Point",
        "Token",
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point() | Token()"
