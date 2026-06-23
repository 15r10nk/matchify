import libcst as cst

from matchify.transform import IfToMatchTransformer


class TestExtractSubject:
    """Test the _extract_subject helper method."""

    def test_extract_subject_from_simple_equality(self):
        """Test extracting subject from simple equality comparison."""
        transformer = IfToMatchTransformer()

        source = "x == 1"
        test_expr = cst.parse_expression(source)

        subject = transformer._extract_subject(test_expr)
        assert subject is not None
        assert subject.deep_equals(cst.parse_expression("x"))

    def test_extract_subject_from_non_equality(self):
        """Test that non-equality comparisons return None."""
        transformer = IfToMatchTransformer()

        source = "x > 5"
        test_expr = cst.parse_expression(source)

        subject = transformer._extract_subject(test_expr)
        assert subject is None

    def test_extract_subject_from_complex_expression(self):
        """Test extracting subject from attribute access."""
        transformer = IfToMatchTransformer()

        source = "obj.attr == 'value'"
        test_expr = cst.parse_expression(source)

        subject = transformer._extract_subject(test_expr)
        assert subject is not None
        assert subject.deep_equals(cst.parse_expression("obj.attr"))
