import pytest

from matchify.sequence_patterns import build_match_pattern_from_info


class TestSequencePatternHelpers:
    def test_unknown_sequence_element_pattern_raises_error(self):
        """Test that unsupported sequence element objects fail loudly."""
        with pytest.raises(TypeError, match="Unsupported sequence element pattern"):
            build_match_pattern_from_info(object())  # type: ignore[arg-type]
