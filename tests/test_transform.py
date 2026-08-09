from textwrap import dedent

import libcst as cst
from helpers import check_code

from matchify.access_path import AccessPath, MatchSubjectPlan
from matchify.assumptions import Assumptions
from matchify.conditions import parse_condition
from matchify.pattern_builder import normalize_condition


class TestTransformCode:
    """Test source-to-source transformation behavior."""

    def test_composite_subject_plan_builds_a_tuple_pattern(self):
        condition = parse_condition(cst.parse_expression("a.x == 1 and b.y == 2"))
        plan = MatchSubjectPlan.from_subjects(
            (
                AccessPath.from_expression(cst.parse_expression("a.x")),
                AccessPath.from_expression(cst.parse_expression("b.y")),
            )
        )

        facts = normalize_condition(condition, plan)

        assert facts.pattern is not None
        assert cst.Module([]).code_for_node(facts.pattern.render()) == "1, 2"
        assert facts.guard is None

    def test_assumed_pure_and_subjects_use_a_composite_match_subject(self):
        source = dedent(
            """
            class Box:
                def __init__(self, x=None, y=None):
                    self.x = x
                    self.y = y

            a = Box(x=1)
            b = Box(y=2)
            if a.x == 1 and b.y == 2:
                print("first")
            elif a.x == 3 and b.y == 4:
                print("second")
            """
        ).strip()

        expected_without_flag = dedent(
            """
            class Box:
                def __init__(self, x=None, y=None):
                    self.x = x
                    self.y = y

            a = Box(x=1)
            b = Box(y=2)
            match a.x:
                case 1 if b.y == 2:
                    print("first")
                case 3 if b.y == 4:
                    print("second")
            """
        ).strip()

        check_code(source, expected_without_flag)
        check_code(
            source,
            expected_without_flag,
            assumptions=Assumptions.from_names({"use-object"}),
        )

        expected_with_flag = dedent(
            """
            class Box:
                def __init__(self, x=None, y=None):
                    self.x = x
                    self.y = y

            a = Box(x=1)
            b = Box(y=2)
            match (a.x, b.y):
                case 1, 2:
                    print("first")
                case 3, 4:
                    print("second")
            """
        ).strip()

        check_code(source, expected_with_flag, assume_pure_subjects=True)

    def test_assumed_pure_subject_used_by_a_majority_joins_match_subject(self):
        source = dedent(
            """
            if op == Op.ADD:
                print("add")
            elif op == Op.SUBTRACT and op2 == Op.ADD:
                print("subtract add")
            elif op == Op.SUBTRACT and op2 == Op.SUBTRACT:
                print("subtract subtract")
            """
        ).strip()

        expected = dedent(
            """
            match (op, op2):
                case Op.ADD, _:
                    print("add")
                case Op.SUBTRACT, Op.ADD:
                    print("subtract add")
                case Op.SUBTRACT, Op.SUBTRACT:
                    print("subtract subtract")
            """
        ).strip()

        check_code(source, expected, assume_pure_subjects=True)

    def test_assumed_pure_attribute_subject_uses_object_patterns(self):
        source = dedent(
            """
            class Value:
                i = 5
                j = 6

            value = Value()
            if value.i == 5:
                print("i")
            elif value.j == 6:
                print("j")
            """
        ).strip()

        expected = dedent(
            """
            class Value:
                i = 5
                j = 6

            value = Value()
            match value:
                case object(i=5):
                    print("i")
                case object(j=6):
                    print("j")
            """
        ).strip()

        check_code(source, source)
        check_code(source, source, assume_pure_subjects=True)
        check_code(
            source,
            expected,
            assumptions=Assumptions.from_names({"use-object"}),
        )

    def test_list_tuple_sequence_checks_require_both_assumptions(self):
        source = dedent(
            """
            value = [1, 2]
            if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1:
                print("one")
            elif isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 2:
                print("two")
        """
        ).strip()

        expected_safe = dedent(
            """
            value = [1, 2]
            match value:
                case 1, _ if isinstance(value, (list, tuple)):
                    print("one")
                case 2, _ if isinstance(value, (list, tuple)):
                    print("two")
        """
        ).strip()

        check_code(source, expected_safe)
        check_code(
            source,
            expected_safe,
            assumptions=Assumptions.from_names({"list-sequence-pattern"}),
        )
        check_code(
            source,
            expected_safe,
            assumptions=Assumptions.from_names({"tuple-sequence-pattern"}),
        )
        check_code(
            source,
            expected_safe.replace(" if isinstance(value, (list, tuple))", ""),
            assumptions=Assumptions.from_names(
                {"list-sequence-pattern", "tuple-sequence-pattern"}
            ),
        )

    def test_qualified_identity_requires_identity_equality_assumption(self):
        """Qualified identity checks need an explicit equality-semantics assumption."""
        source = dedent(
            """
            class Kind:
                START = object()
                STOP = object()

            kind = Kind.START
            if kind is Kind.START:
                print("start")
            elif kind is Kind.STOP:
                print("stop")
            else:
                print("other")
        """
        ).strip()

        expected = dedent(
            """
            class Kind:
                START = object()
                STOP = object()

            kind = Kind.START
            match kind:
                case Kind.START:
                    print("start")
                case Kind.STOP:
                    print("stop")
                case _:
                    print("other")
        """
        ).strip()

        check_code(source, source)
        check_code(
            source,
            expected,
            assumptions=Assumptions.from_names({"identity-equality"}),
        )

    def test_literal_set_membership_requires_hashable_subjects_assumption(self):
        source = dedent(
            """
            option = "-h"
            if option in {"-h", "--help"}:
                print("help")
            elif option in {"-V", "--version"}:
                print("version")
            """
        ).strip()

        expected = dedent(
            """
            option = "-h"
            match option:
                case "-h" | "--help":
                    print("help")
                case "-V" | "--version":
                    print("version")
            """
        ).strip()

        check_code(source, source)
        check_code(
            source,
            expected,
            assumptions=Assumptions.from_names({"hashable-subjects"}),
        )

    def test_unsafe_set_membership_is_not_converted(self):
        source = dedent(
            """
            values = {"a"}
            if value in {*values}:
                print("starred")
            elif value in {"b"}:
                print("literal")

            if value in {make_value()}:
                print("dynamic")
            elif value in {"b"}:
                print("literal")

            if value in {Constants.VALUE}:
                print("qualified")
            elif value in {"b"}:
                print("literal")

            if value in {"a", "a"}:
                print("duplicate")
            elif value in {"b"}:
                print("literal")
            """
        ).strip()

        check_code(
            source,
            source,
            assumptions=Assumptions.from_names({"hashable-subjects"}),
        )

    def test_or_pattern_with_safe_sequence_alternative(self):
        """Test safe sequence type checks do not block top-level sequence OR patterns."""
        source = dedent(
            """
            value = [1, 2]
            if (isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1 and value[1] == 2) or value is None:
                print("match")
            elif value is False:
                print("false")
        """
        ).strip()

        expected_safe = dedent(
            """
            value = [1, 2]
            match value:
                case _ if (isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1 and value[1] == 2) or value is None:
                    print("match")
                case False:
                    print("false")
        """
        ).strip()

        check_code(source, expected_safe)
        check_code(
            source,
            expected_safe.replace(
                "case _ if (isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == 1 and value[1] == 2) or value is None:",
                "case [1, 2] | None:",
            ),
            assumptions=Assumptions.from_names(
                {"list-sequence-pattern", "tuple-sequence-pattern"}
            ),
        )

    def test_or_pattern_with_safe_sequence_attribute_alternative(self):
        """Test safe sequence type checks do not block class sequence OR patterns."""
        source = dedent(
            """
            class Point:
                def __init__(self, **attrs):
                    self.__dict__.update(attrs)

            value = Point(items=[1, None])
            if (isinstance(value, Point) and hasattr(value, "items") and isinstance(value.items, (list, tuple)) and len(value.items) == 2 and value.items[0] == 1 and value.items[1] is None) or value == 0:
                print("match")
            elif value is None:
                print("none")
        """
        ).strip()

        expected_safe = dedent(
            """
            class Point:
                def __init__(self, **attrs):
                    self.__dict__.update(attrs)

            value = Point(items=[1, None])
            match value:
                case _ if (isinstance(value, Point) and hasattr(value, "items") and isinstance(value.items, (list, tuple)) and len(value.items) == 2 and value.items[0] == 1 and value.items[1] is None) or value == 0:
                    print("match")
                case None:
                    print("none")
        """
        ).strip()

        check_code(source, expected_safe)
        check_code(
            source,
            expected_safe.replace(
                'case _ if (isinstance(value, Point) and hasattr(value, "items") and isinstance(value.items, (list, tuple)) and len(value.items) == 2 and value.items[0] == 1 and value.items[1] is None) or value == 0:',
                "case Point(items=[1, None]) | 0:",
            ),
            assumptions=Assumptions.from_names(
                {"list-sequence-pattern", "tuple-sequence-pattern"}
            ),
        )
