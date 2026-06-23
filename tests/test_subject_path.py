import libcst as cst

from matchify.subject_path import AttributePathPart, SubjectPath, SubscriptPathPart


class TestSubjectPath:
    """Test the shared subject-derived expression helper."""

    def test_subject_itself_has_empty_path(self):
        subject = cst.parse_expression("node")
        path = SubjectPath.from_expression(subject, subject)

        assert path is not None
        assert path.is_subject
        assert path.parts == ()

    def test_attribute_path_extracts_names(self):
        subject = cst.parse_expression("node")
        expr = cst.parse_expression("node.child.value")

        path = SubjectPath.from_expression(expr, subject)

        assert path is not None
        assert path.attribute_names == ("child", "value")
        assert path.direct_attribute_name is None

    def test_direct_attribute_name(self):
        subject = cst.parse_expression("node")
        expr = cst.parse_expression("node.kind")

        path = SubjectPath.from_expression(expr, subject)

        assert path is not None
        assert path.direct_attribute_name == "kind"

    def test_subscript_path_extracts_indices(self):
        subject = cst.parse_expression("node")
        expr = cst.parse_expression("node.args[0]")

        path = SubjectPath.from_expression(expr, subject)

        assert path is not None
        assert path.parts == (AttributePathPart("args"), SubscriptPathPart(0))
        assert path.attribute_names is None

    def test_unrelated_expression_returns_none(self):
        subject = cst.parse_expression("node")
        expr = cst.parse_expression("other.value")

        assert SubjectPath.from_expression(expr, subject) is None
