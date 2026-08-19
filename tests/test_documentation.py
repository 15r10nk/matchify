import re
import shlex
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
import pytest

from matchify.assumptions import Assumptions
from matchify.transform import transform_code


@dataclass(frozen=True)
class DocumentationExample:
    source: Path
    index: int
    code: str
    assumption: str | None


@dataclass(frozen=True)
class SelectiveConversionExample:
    index: int
    before: str
    after: str
    convert_if: str


def documentation_examples() -> list[DocumentationExample]:
    examples = []
    for path in (Path("README.md"), Path("docs/assumptions.md")):
        source = path.read_text(encoding="utf-8")
        for index, match in enumerate(
            re.finditer(r"```([^\n]*)\n(.*?)```", source, re.DOTALL), start=1
        ):
            if match.group(1).strip() != "python":
                continue
            examples.append(
                DocumentationExample(
                    source=path,
                    index=index,
                    code=match.group(2).strip(),
                    assumption=_preceding_assumption(source[: match.start()]),
                )
            )
    return examples


def _preceding_assumption(source: str) -> str | None:
    headings = re.findall(r"^#{1,6} .+$", source, re.MULTILINE)
    if not headings:
        return None
    match = re.fullmatch(r"#{2,6} `--assume=([a-z-]+)`", headings[-1])
    return match.group(1) if match else None


def split_before_after_example(code: str) -> tuple[str, str]:
    before, marker, after = code.partition("# After")
    assert marker, "Python example needs a '# After' marker"
    assert before.startswith("# Before\n"), "Python example needs a '# Before' marker"
    return before.removeprefix("# Before\n").strip(), after.strip()


def test_preceding_assumption_is_scoped_to_its_section():
    assumption_heading = "### `--assume=pure-subjects`\n"

    assert _preceding_assumption(assumption_heading) == "pure-subjects"
    assert _preceding_assumption(f"{assumption_heading}\n## Development\n") is None


@pytest.mark.parametrize(
    "example",
    documentation_examples(),
    ids=lambda example: f"{example.source.stem}-{example.index}",
)
def test_documentation_example(example: DocumentationExample):
    before, after = split_before_after_example(example.code)
    cst.parse_module(before)
    cst.parse_module(after)
    assumptions = Assumptions.from_names(
        [example.assumption] if example.assumption is not None else None
    )

    assert transform_code(before, assumptions=assumptions).strip() == after


def test_index_generates_readme_with_markdown_exec():
    index = Path("docs/index.md").read_text(encoding="utf-8")

    assert '```python exec="on"' in index
    assert 'Path("README.md").read_text' in index
    assert '"NOTE": ("note", None)' in index
    assert "while i < len(feedback)" in index


def selective_conversion_examples() -> list[SelectiveConversionExample]:
    source = Path("docs/selective-conversion.md").read_text(encoding="utf-8")
    examples = []
    for index, match in enumerate(
        re.finditer(r"```python\n(.*?)```", source, re.DOTALL), start=1
    ):
        code = match.group(1)
        before, marker, after = code.partition("# After:")
        assert marker, f"Python example {index} needs a '# After:' command"
        command, separator, after = after.partition("\n")
        assert separator, f"Python example {index} needs code after '# After:'"
        arguments = shlex.split(command.strip())
        assert arguments[:2] == ["matchify", "--convert-if"]
        assert len(arguments) == 3
        examples.append(
            SelectiveConversionExample(
                index=index,
                before=before.removeprefix("# Before\n").strip(),
                after=after.strip(),
                convert_if=arguments[2],
            )
        )
    return examples


@pytest.mark.parametrize(
    "example",
    selective_conversion_examples(),
    ids=lambda example: f"example-{example.index}",
)
def test_selective_conversion_example(example: SelectiveConversionExample):
    assert transform_code(example.before, convert_if=example.convert_if).strip() == (
        example.after
    )
