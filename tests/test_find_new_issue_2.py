from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from find_new_issue_2 import (  # noqa: E402
    CapturePattern,
    ClassPattern,
    IfStyle,
    LiteralPattern,
    RenderContext,
    SequencePattern,
    WildcardPattern,
)


def test_wildcards_do_not_emit_trivial_nested_conditions():
    context = RenderContext(random.Random(1), IfStyle.CANONICAL)
    pattern = SequencePattern(
        (WildcardPattern(), LiteralPattern("1"), CapturePattern("captured")),
        star=True,
    )

    assert pattern.render_if("value", context) == (
        "isinstance(value, (list, tuple)) " "and len(value) >= 3 " "and value[1] == 1"
    )


def test_class_wildcard_attribute_checks_existence_without_true_condition():
    context = RenderContext(random.Random(1), IfStyle.CANONICAL)
    pattern = ClassPattern("Point", (("x", WildcardPattern()),))

    assert pattern.render_if("value", context) == (
        "isinstance(value, Point) and hasattr(value, 'x')"
    )
