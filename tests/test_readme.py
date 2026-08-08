import re
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
import pytest

from matchify.assumptions import Assumptions
from matchify.transform import transform_code


@dataclass(frozen=True)
class CodeBlock:
    index: int
    language: str
    code: str
    assumption: str | None


def readme_python_code_blocks() -> list[CodeBlock]:
    text = Path("README.md").read_text(encoding="utf-8")
    blocks = []
    for index, match in enumerate(
        re.finditer(r"```([^\n]*)\n(.*?)```", text, re.DOTALL), start=1
    ):
        language = match.group(1).strip()
        if language != "python":
            continue
        blocks.append(
            CodeBlock(
                index=index,
                language=language,
                code=match.group(2).strip(),
                assumption=_preceding_assumption(text[: match.start()]),
            )
        )
    return blocks


def _preceding_assumption(text: str) -> str | None:
    headings = re.findall(r"^#{1,6} .+$", text, re.MULTILINE)
    if not headings:
        return None
    match = re.fullmatch(r"### `--assume=([a-z-]+)`", headings[-1])
    return match.group(1) if match else None


def test_preceding_assumption_is_scoped_to_its_section():
    assumption_heading = "### `--assume=pure-subjects`\n"

    assert _preceding_assumption(assumption_heading) == "pure-subjects"
    assert _preceding_assumption(f"{assumption_heading}\n## Development\n") is None


@pytest.mark.parametrize(
    "block",
    readme_python_code_blocks(),
    ids=lambda block: f"block-{block.index}",
)
def test_readme_python_code_blocks(block: CodeBlock):
    before, after = split_before_after_example(block)

    cst.parse_module(before)
    cst.parse_module(after)

    assumptions = Assumptions.from_names(
        [block.assumption] if block.assumption is not None else None
    )
    assert transform_code(before, assumptions=assumptions).strip() == after


def split_before_after_example(block: CodeBlock) -> tuple[str, str]:
    before_marker = "# Before"
    after_marker = "# After"
    assert before_marker in block.code
    assert after_marker in block.code

    before, after = block.code.split(after_marker, 1)
    before = before.replace(before_marker, "", 1).strip()
    after = after.strip()
    return before, after
