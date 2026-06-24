import libcst as cst

from matchify.facts import ClassFact, OrFact, SequenceFact, ValueFact
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


def test_normalize_branch_builds_class_attribute_value_facts():
    facts = normalize("isinstance(value, Point) and value.x == 1", "value")

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ClassFact)
    assert isinstance(facts.facts[1], ValueFact)
    assert facts.facts[1].path.direct_attribute_name == "x"
    assert cst.Module([]).code_for_node(facts.facts[1].value) == "1"
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point(x=1)"


def test_normalize_branch_builds_class_union_attribute_value_facts():
    facts = normalize(
        "isinstance(value, (Point, Token)) and value.kind is None", "value"
    )

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ClassFact)
    assert isinstance(facts.facts[1], ValueFact)
    assert facts.facts[1].path.direct_attribute_name == "kind"
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(kind=None) | Token(kind=None)"
    )


def test_normalize_branch_builds_class_attribute_class_facts():
    facts = normalize(
        "isinstance(value, NameExpr) and isinstance(value.node, Var)", "value"
    )

    assert facts.pattern is not None
    assert isinstance(facts.facts[0], ClassFact)
    assert isinstance(facts.facts[1], ClassFact)
    assert facts.facts[1].path.direct_attribute_name == "node"
    assert [cst.Module([]).code_for_node(cls) for cls in facts.facts[1].classes] == [
        "Var"
    ]
    assert (
        cst.Module([]).code_for_node(facts.pattern.render()) == "NameExpr(node=Var())"
    )


def test_normalize_branch_combines_attribute_value_and_class_facts():
    facts = normalize(
        "isinstance(value, NameExpr) and value.kind is None and isinstance(value.node, Var)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ValueFact, ClassFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "NameExpr(kind=None, node=Var())"
    )


def test_normalize_branch_builds_nested_attribute_value_facts():
    facts = normalize(
        "isinstance(value, NameExpr) and isinstance(value.node, Var) and value.node.type is None",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ValueFact, ClassFact]
    assert facts.facts[1].path.attribute_names == ("node", "type")
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "NameExpr(node=Var(type=None))"
    )


def test_normalize_branch_builds_nested_attribute_class_facts():
    facts = normalize(
        "isinstance(value, NameExpr) and isinstance(value.node, Var) and isinstance(value.node.type, TypeInfo)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ClassFact, ClassFact]
    assert facts.facts[1].path.attribute_names == ("node",)
    assert facts.facts[2].path.attribute_names == ("node", "type")
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "NameExpr(node=Var(type=TypeInfo()))"
    )


def test_normalize_branch_builds_or_value_facts():
    facts = normalize("value == 1 or value == 2", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ValueFact, ValueFact]
    assert all(fact.path.is_subject for fact in facts.facts)
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1 | 2"


def test_normalize_branch_builds_or_class_facts():
    facts = normalize("isinstance(value, Point) or isinstance(value, Token)", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ClassFact]
    assert all(fact.path.is_subject for fact in facts.facts)
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point() | Token()"


def test_normalize_branch_builds_or_class_attribute_facts():
    facts = normalize(
        "(isinstance(value, Point) and value.x == 1) or "
        "(isinstance(value, Token) and value.kind is None)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        ValueFact,
        ClassFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(x=1) | Token(kind=None)"
    )


def test_normalize_branch_builds_safe_or_class_attribute_facts():
    facts = normalize(
        "(isinstance(value, Point) and hasattr(value, 'kind') and "
        "value.kind == 1) or isinstance(value, Token)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        ValueFact,
        ClassFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(kind=1) | Token()"
    )
    assert facts.guard is None


def test_normalize_branch_builds_value_fact_with_guard():
    facts = normalize("value == 1 and ENABLED", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ValueFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1"
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == "ENABLED"


def test_normalize_branch_builds_class_attribute_facts_with_guard():
    facts = normalize("isinstance(value, Point) and value.x == 1 and ENABLED", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ValueFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point(x=1)"
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == "ENABLED"


def test_normalize_branch_drops_redundant_safe_class_attribute_checks():
    facts = normalize(
        "isinstance(value, Point) and hasattr(value, 'kind') and value.kind == 1",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ValueFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point(kind=1)"
    assert facts.guard is None


def test_normalize_branch_drops_redundant_safe_nested_class_attribute_checks():
    facts = normalize(
        "isinstance(value, Point) and hasattr(value, 'x') and "
        "isinstance(value.x, Node) and hasattr(value.x, 'kind') and "
        "value.x.kind == 1",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, ValueFact, ClassFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(x=Node(kind=1))"
    )
    assert facts.guard is None


def test_normalize_branch_drops_redundant_subject_sequence_type_guard():
    facts = normalize(
        "isinstance(value, (list, tuple)) and len(value) == 2 and "
        "value[0] == 1 and value[1] == 2",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1, 2"
    assert facts.guard is None


def test_normalize_branch_builds_or_facts_with_common_guard():
    facts = normalize(
        "(value == 1 and ENABLED) or (value == 2 and ENABLED)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ValueFact, ValueFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1 | 2"
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == "ENABLED"


def test_normalize_branch_builds_class_attribute_or_fact():
    facts = normalize(
        "isinstance(value, Point) and (value.x == 1 or value.x == 2)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, OrFact]
    assert facts.facts[1].path.attribute_names == ("x",)
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point(x=1 | 2)"


def test_normalize_branch_builds_nested_class_attribute_or_fact():
    facts = normalize(
        "isinstance(value, Point) and isinstance(value.data, Data) and "
        "(value.data.kind == 1 or value.data.kind == 2)",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, OrFact, ClassFact]
    assert facts.facts[1].path.attribute_names == ("data", "kind")
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(data=Data(kind=1 | 2))"
    )


def test_normalize_branch_builds_sequence_value_facts():
    facts = normalize("len(value) == 2 and value[0] == 1 and value[1] == 2", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1, 2"


def test_normalize_branch_builds_sequence_class_facts():
    facts = normalize(
        "len(value) == 2 and isinstance(value[0], Point) and value[1] is None",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ClassFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "Point(), None"


def test_normalize_branch_builds_sequence_class_attribute_facts():
    facts = normalize(
        "len(value) == 1 and isinstance(value[0], Point) and "
        "value[0].x == 1 and value[0].y == 2",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ValueFact,
        ClassFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == ("Point(x=1, y=2),")


def test_normalize_branch_builds_sequence_nested_class_attribute_facts():
    facts = normalize(
        "len(value) == 1 and isinstance(value[0], Point) and "
        "isinstance(value[0].x, Node) and value[0].x.kind == 'ready'",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ClassFact,
        ClassFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(x=Node(kind='ready')),"
    )


def test_normalize_branch_builds_sequence_wildcard_facts():
    facts = normalize("len(value) == 3 and value[0] == 1 and value[2] == 3", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1, _, 3"


def test_normalize_branch_builds_sequence_or_element_fact():
    facts = normalize(
        "len(value) == 2 and (value[0] == 1 or value[0] == 2) and value[1] == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        OrFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1 | 2, 3"


def test_normalize_branch_builds_sequence_class_attribute_or_fact():
    facts = normalize(
        "len(value) == 1 and "
        "((isinstance(value[0], Point) and value[0].kind == 1) or "
        "(isinstance(value[0], Token) and value[0].kind == 2))",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [SequenceFact, OrFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(kind=1) | Token(kind=2),"
    )


def test_normalize_branch_builds_sequence_nested_class_attribute_or_fact():
    facts = normalize(
        "len(value) == 1 and "
        "((isinstance(value[0], Point) and isinstance(value[0].node, Node) "
        "and value[0].node.kind == 1) or isinstance(value[0], Token))",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [SequenceFact, OrFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(node=Node(kind=1)) | Token(),"
    )


def test_normalize_branch_builds_sequence_star_facts():
    facts = normalize("len(value) >= 2 and value[0] == 1 and value[1] == 2", "value")

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "1, 2, *_"


def test_normalize_branch_builds_nested_sequence_facts():
    facts = normalize(
        "len(value) == 2 and len(value[0]) == 2 and "
        "value[0][0] == 1 and value[0][1] == 2 and value[1] == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        SequenceFact,
        ValueFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "[1, 2], 3"


def test_normalize_branch_builds_nested_sequence_facts_independent_of_len_order():
    facts = normalize(
        "len(value[0]) == 2 and len(value) == 2 and "
        "value[0][0] == 1 and value[0][1] == 2 and value[1] == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        SequenceFact,
        ValueFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "[1, 2], 3"


def test_normalize_branch_builds_nested_sequence_or_facts():
    facts = normalize(
        "len(value) == 1 and len(value[0]) == 2 and "
        "(value[0][0] == 1 or value[0][0] == 2) and value[0][1] == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        SequenceFact,
        OrFact,
        SequenceFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == "[1 | 2, 3],"


def test_normalize_branch_builds_sequence_or_pattern_tree_element_fact():
    facts = normalize(
        "len(value) == 1 and "
        "((len(value[0]) >= 2 and value[0][1] == 2) or "
        "(len(value[0]) >= 2 and value[0][1] == 3))",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [SequenceFact, OrFact]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "[_, 2, *_] | [_, 3, *_],"
    )


def test_normalize_branch_builds_class_sequence_attribute_facts():
    facts = normalize(
        "isinstance(value, Data) and len(value.items) == 3 and "
        "value.items[0] == 1 and value.items[1] == 2 and value.items[2] == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        ValueFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Data(items=[1, 2, 3])"
    )


def test_normalize_branch_builds_class_sequence_and_scalar_attribute_facts():
    facts = normalize(
        "isinstance(value, Container) and len(value.items) == 3 and "
        "value.items[0] == 1 and value.items[1] == 2 and value.items[2] == 3 "
        "and value.count == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        ValueFact,
        ValueFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Container(items=[1, 2, 3], count=3)"
    )


def test_normalize_branch_builds_class_sequence_attribute_facts_with_guard():
    facts = normalize(
        "isinstance(value, Data) and len(value.items) == 2 and "
        "value.items[0] == 1 and value.items[1] == 2 and ENABLED",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Data(items=[1, 2])"
    )
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == "ENABLED"


def test_normalize_branch_preserves_safe_class_sequence_attribute_type_guard():
    facts = normalize(
        "isinstance(value, Data) and hasattr(value, 'items') and "
        "isinstance(value.items, (list, tuple)) and len(value.items) == 2 and "
        "value.items[0] == 1 and value.items[1] is None",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Data(items=[1, None])"
    )
    assert facts.guard is not None
    assert cst.Module([]).code_for_node(facts.guard) == (
        "isinstance(value.items, (list, tuple))"
    )


def test_normalize_branch_builds_class_sequence_attribute_star_facts():
    facts = normalize(
        "isinstance(value, Data) and len(value.items) >= 2 and "
        "value.items[0] == 1 and value.items[1] == 2",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Data(items=[1, 2, *_])"
    )


def test_normalize_branch_builds_nested_class_sequence_attribute_facts():
    facts = normalize(
        "isinstance(value, Data) and len(value.items) == 1 and "
        "len(value.items[0]) == 2 and value.items[0][0] == 1 and "
        "value.items[0][1] == 2",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        SequenceFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Data(items=[[1, 2]])"
    )


def test_normalize_branch_builds_sequence_element_class_sequence_attribute_facts():
    facts = normalize(
        "isinstance(value, Data) and len(value.items) == 1 and "
        "isinstance(value.items[0], Data) and len(value.items[0].items) == 3 and "
        "value.items[0].items[0] == 1 and value.items[0].items[1] == 2 and "
        "value.items[0].items[2] == 3",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        SequenceFact,
        ValueFact,
        ValueFact,
        ValueFact,
        ClassFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Data(items=[Data(items=[1, 2, 3])])"
    )


def test_normalize_branch_builds_class_sequence_attribute_or_pattern_tree_fact():
    facts = normalize(
        "isinstance(value, Wrapper) and "
        "((len(value.data) >= 2 and value.data[1] == 2) or "
        "(len(value.data) >= 2 and value.data[1] == 3))",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [ClassFact, OrFact]
    assert facts.facts[1].path.attribute_names == ("data",)
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Wrapper(data=[_, 2, *_] | [_, 3, *_])"
    )


def test_normalize_branch_builds_safe_or_class_sequence_attribute_facts():
    facts = normalize(
        "(isinstance(value, Point) and hasattr(value, 'items') and "
        "isinstance(value.items, (list, tuple)) and len(value.items) == 2 and "
        "value.items[0] == 1 and value.items[1] is None) or value == 0",
        "value",
    )

    assert facts.pattern is not None
    assert [type(fact) for fact in facts.facts] == [
        ClassFact,
        SequenceFact,
        ValueFact,
        ValueFact,
        ValueFact,
    ]
    assert cst.Module([]).code_for_node(facts.pattern.render()) == (
        "Point(items=[1, None]) | 0"
    )
    assert facts.guard is None
