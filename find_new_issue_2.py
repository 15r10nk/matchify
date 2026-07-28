from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Protocol

from matchify.assumptions import Assumptions
from matchify.cli import convert_file

SAMPLES_DIR = Path("tests/samples")
CLASS_NAMES = ("Point", "Token", "Node")
ATTR_NAMES = ("x", "y", "kind", "items")
LITERALS = ("-1", "0", "1", "2", "'red'", "'ready'")
SINGLETONS = ("None", "True", "False")


class IfStyle(Enum):
    CANONICAL = "canonical"
    MEMBERSHIP = "membership"
    TYPE_NONE = "type-none"
    PAREN_CLASSINFO = "paren-classinfo"
    RAW_GUARDS = "raw-guards"
    MIXED = "mixed"


@dataclass(frozen=True)
class RenderContext:
    rng: random.Random
    style: IfStyle

    def choose_style(self, *styles: IfStyle) -> bool:
        return self.style in styles or (
            self.style is IfStyle.MIXED and self.rng.choice([True, False])
        )


class Pattern(Protocol):
    def render_match(self) -> str: ...

    def render_if(self, subject: str, context: RenderContext) -> str: ...

    def matching_value(self) -> str: ...

    def nonmatching_value(self) -> str: ...

    def capture_names(self) -> tuple[str, ...]: ...

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class LiteralPattern:
    value: str

    def render_match(self) -> str:
        return self.value

    def render_if(self, subject: str, context: RenderContext) -> str:
        return f"{subject} == {self.value}"

    def matching_value(self) -> str:
        return self.value

    def nonmatching_value(self) -> str:
        return "'miss'" if self.value.startswith("'") else "99"

    def capture_names(self) -> tuple[str, ...]:
        return ()

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class SingletonPattern:
    value: str

    def render_match(self) -> str:
        return self.value

    def render_if(self, subject: str, context: RenderContext) -> str:
        return f"{subject} is {self.value}"

    def matching_value(self) -> str:
        return self.value

    def nonmatching_value(self) -> str:
        return "object()"

    def capture_names(self) -> tuple[str, ...]:
        return ()

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class CapturePattern:
    name: str

    def render_match(self) -> str:
        return self.name

    def render_if(self, subject: str, context: RenderContext) -> str:
        return "True"

    def matching_value(self) -> str:
        return "42"

    def nonmatching_value(self) -> str:
        return "42"

    def capture_names(self) -> tuple[str, ...]:
        return (self.name,)

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return (f"{self.name} = {subject}",)


@dataclass(frozen=True)
class WildcardPattern:
    def render_match(self) -> str:
        return "_"

    def render_if(self, subject: str, context: RenderContext) -> str:
        return "True"

    def matching_value(self) -> str:
        return "object()"

    def nonmatching_value(self) -> str:
        return "object()"

    def capture_names(self) -> tuple[str, ...]:
        return ()

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class OrPattern:
    alternatives: tuple[Pattern, ...]

    def render_match(self) -> str:
        return " | ".join(pattern.render_match() for pattern in self.alternatives)

    def render_if(self, subject: str, context: RenderContext) -> str:
        if (
            context.choose_style(IfStyle.MEMBERSHIP)
            and self._all_literal_alternatives()
            and not self.capture_names()
        ):
            values = ", ".join(
                pattern.value  # type: ignore[attr-defined]
                for pattern in self.alternatives
            )
            return f"{subject} in ({values},)"
        return (
            "("
            + " or ".join(
                pattern.render_if(subject, context) for pattern in self.alternatives
            )
            + ")"
        )

    def matching_value(self) -> str:
        return self.alternatives[0].matching_value()

    def nonmatching_value(self) -> str:
        return self.alternatives[0].nonmatching_value()

    def capture_names(self) -> tuple[str, ...]:
        names = self.alternatives[0].capture_names()
        if all(pattern.capture_names() == names for pattern in self.alternatives[1:]):
            return names
        return ()

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        if not self.capture_names():
            return ()
        return self.alternatives[0].if_capture_assignments(subject)

    def _all_literal_alternatives(self) -> bool:
        return all(isinstance(pattern, LiteralPattern) for pattern in self.alternatives)


@dataclass(frozen=True)
class ClassPattern:
    class_name: str
    attrs: tuple[tuple[str, Pattern], ...] = ()

    def render_match(self) -> str:
        if not self.attrs:
            return f"{self.class_name}()"
        args = ", ".join(
            f"{name}={pattern.render_match()}" for name, pattern in self.attrs
        )
        return f"{self.class_name}({args})"

    def render_if(self, subject: str, context: RenderContext) -> str:
        parts = [f"isinstance({subject}, {self._classinfo(context)})"]
        for attr, pattern in self.attrs:
            parts.append(f"hasattr({subject}, {attr!r})")
            parts.append(pattern.render_if(f"{subject}.{attr}", context))
        return " and ".join(parts)

    def matching_value(self) -> str:
        if not self.attrs:
            return f"{self.class_name}()"
        args = ", ".join(
            f"{name}={pattern.matching_value()}" for name, pattern in self.attrs
        )
        return f"{self.class_name}({args})"

    def nonmatching_value(self) -> str:
        if not self.attrs:
            return "object()"
        attr, pattern = self.attrs[0]
        args = [f"{attr}={pattern.nonmatching_value()}"]
        args.extend(
            f"{name}={other.matching_value()}" for name, other in self.attrs[1:]
        )
        return f"{self.class_name}({', '.join(args)})"

    def capture_names(self) -> tuple[str, ...]:
        return tuple(
            name for _, pattern in self.attrs for name in pattern.capture_names()
        )

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return tuple(
            assignment
            for attr, pattern in self.attrs
            for assignment in pattern.if_capture_assignments(f"{subject}.{attr}")
        )

    def _classinfo(self, context: RenderContext) -> str:
        if self.class_name == "NoneType" or context.choose_style(IfStyle.TYPE_NONE):
            if self.class_name == "NoneType":
                return "type(None)"
        if context.choose_style(IfStyle.PAREN_CLASSINFO):
            return f"({self.class_name})"
        return self.class_name


@dataclass(frozen=True)
class NoneTypeOrClassPattern:
    class_name: str

    def render_match(self) -> str:
        return f"None | {self.class_name}()"

    def render_if(self, subject: str, context: RenderContext) -> str:
        if context.choose_style(IfStyle.TYPE_NONE):
            return f"isinstance({subject}, (type(None), {self.class_name}))"
        return f"({subject} is None or isinstance({subject}, {self.class_name}))"

    def matching_value(self) -> str:
        return "None"

    def nonmatching_value(self) -> str:
        return "object()"

    def capture_names(self) -> tuple[str, ...]:
        return ()

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class SequencePattern:
    elements: tuple[Pattern, ...]
    star: bool = False
    tuple_value: bool = False

    def render_match(self) -> str:
        parts = [pattern.render_match() for pattern in self.elements]
        if self.star:
            parts.append("*_")
        return "[" + ", ".join(parts) + "]"

    def render_if(self, subject: str, context: RenderContext) -> str:
        op = ">=" if self.star else "=="
        parts = [
            f"isinstance({subject}, (list, tuple))",
            f"len({subject}) {op} {len(self.elements)}",
        ]
        for index, pattern in enumerate(self.elements):
            parts.append(pattern.render_if(f"{subject}[{index}]", context))
        return " and ".join(parts)

    def matching_value(self) -> str:
        values = [pattern.matching_value() for pattern in self.elements]
        if self.star:
            values.append("object()")
        return render_sequence_value(values, self.tuple_value)

    def nonmatching_value(self) -> str:
        if not self.elements:
            return "object()"
        values = [self.elements[0].nonmatching_value()]
        values.extend(pattern.matching_value() for pattern in self.elements[1:])
        return render_sequence_value(values, self.tuple_value)

    def capture_names(self) -> tuple[str, ...]:
        return tuple(
            name for pattern in self.elements for name in pattern.capture_names()
        )

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return tuple(
            assignment
            for index, pattern in enumerate(self.elements)
            for assignment in pattern.if_capture_assignments(f"{subject}[{index}]")
        )


@dataclass(frozen=True)
class GuardedPattern:
    pattern: Pattern
    guard: str

    def render_match(self) -> str:
        return self.pattern.render_match()

    def render_guard(self, subject: str) -> str:
        return self.guard.format(subject=subject)

    def render_if(self, subject: str, context: RenderContext) -> str:
        return f"{self.pattern.render_if(subject, context)} and {self.render_guard(subject)}"

    def matching_value(self) -> str:
        return self.pattern.matching_value()

    def nonmatching_value(self) -> str:
        return self.pattern.nonmatching_value()

    def capture_names(self) -> tuple[str, ...]:
        return self.pattern.capture_names()

    def if_capture_assignments(self, subject: str) -> tuple[str, ...]:
        return self.pattern.if_capture_assignments(subject)


@dataclass(frozen=True)
class Case:
    pattern: Pattern
    body: str


@dataclass(frozen=True)
class Program:
    classes: tuple[str, ...]
    subject: str
    cases: tuple[Case, ...]
    default_body: str | None
    sample_values: tuple[str, ...]

    def class_defs_code(self) -> str:
        return "\n".join(
            f"class {class_name}:\n"
            "    def __init__(self, **attrs):\n"
            "        self.__dict__.update(attrs)\n"
            for class_name in self.classes
        )

    def setup_code(self) -> str:
        return (
            f"{self.class_defs_code()}"
            "def stable_repr(value):\n"
            "    if type(value) is object:\n"
            "        return 'object()'\n"
            "    if hasattr(value, '__dict__'):\n"
            "        attrs = ', '.join(\n"
            "            f'{name}={stable_repr(attr)}'\n"
            "            for name, attr in sorted(value.__dict__.items())\n"
            "        )\n"
            "        return f'{type(value).__name__}({attrs})'\n"
            "    if isinstance(value, list):\n"
            "        return '[' + ', '.join(stable_repr(item) for item in value) + ']'\n"
            "    if isinstance(value, tuple):\n"
            "        inner = ', '.join(stable_repr(item) for item in value)\n"
            "        return f'({inner},)' if len(value) == 1 else f'({inner})'\n"
            "    return repr(value)\n"
            f"values = [\n{self._value_lines()}\n]\n"
        )

    def render_if_code(self, style: IfStyle, seed: int) -> str:
        context = RenderContext(random.Random(seed), style)
        branch_blocks = []
        for index, case in enumerate(self.cases):
            keyword = "if" if index == 0 else "elif"
            condition = case.pattern.render_if(self.subject, context)
            body = indent_code(
                render_body(case, self.subject, include_captures=True), "        "
            )
            branch_blocks.append(f"    {keyword} {condition}:\n{body}")
        if self.default_body is not None:
            branch_blocks.append(f"    else:\n        print({self.default_body!r})")
        return (
            self.setup_code()
            + "for value in values:\n"
            + "\n".join(branch_blocks)
            + "\n"
        )

    def render_match_code(self) -> str:
        case_blocks = []
        for case in self.cases:
            pattern = case.pattern
            guard = ""
            if isinstance(pattern, GuardedPattern):
                guard = f" if {pattern.render_guard(self.subject)}"
            body = indent_code(
                render_body(case, self.subject, include_captures=False), "            "
            )
            case_blocks.append(f"        case {pattern.render_match()}{guard}:\n{body}")
        if self.default_body is not None:
            case_blocks.append(
                f"        case _:\n            print({self.default_body!r})"
            )
        return (
            self.setup_code()
            + "for value in values:\n"
            + f"    match {self.subject}:\n"
            + "\n".join(case_blocks)
            + "\n"
        )

    def _value_lines(self) -> str:
        return "\n".join(f"    {value}," for value in self.sample_values)


@dataclass(frozen=True)
class Issue:
    kind: str
    seed: int
    index: int
    style: str
    original: str
    converted: str
    match_reference: str
    expected_trace: tuple[str, str, type[BaseException] | None]
    actual_trace: tuple[str, str, type[BaseException] | None]
    changed: bool
    error: str | None = None

    def trace_text(self) -> str:
        return format_trace(self.expected_trace)


def render_body(case: Case, subject: str, *, include_captures: bool) -> str:
    names = case.pattern.capture_names()
    capture_lines = (
        list(case.pattern.if_capture_assignments(subject)) if include_captures else []
    )
    if names:
        values = ", ".join(f"stable_repr({name})" for name in names)
        print_line = f"print({case.body!r}, {values})"
    else:
        print_line = f"print({case.body!r})"
    return "\n".join([*capture_lines, print_line])


def render_sequence_value(values: list[str], tuple_value: bool) -> str:
    if not tuple_value:
        return "[" + ", ".join(values) + "]"
    if len(values) == 1:
        return f"({values[0]},)"
    return "(" + ", ".join(values) + ")"


def indent_code(code: str, prefix: str) -> str:
    return "\n".join(f"{prefix}{line}" if line else line for line in code.splitlines())


def execute_result(source: str) -> tuple[str, str, type[BaseException] | None]:
    stdout = StringIO()
    stderr = StringIO()
    exception_type = None
    namespace: dict[str, object] = {}
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exec(source, namespace)
    except BaseException as error:
        exception_type = type(error)
    return ("", stdout.getvalue() + stderr.getvalue(), exception_type)


def exception_name(exception_type: type[BaseException] | None) -> str:
    return "None" if exception_type is None else exception_type.__name__


def format_trace(trace: tuple[str, str, type[BaseException] | None]) -> str:
    return "\n".join(
        [
            f"result: {trace[0]}",
            f"output: {trace[1]!r}",
            f"exception: {exception_name(trace[2])}",
            "",
        ]
    )


def generate_program(rng: random.Random) -> Program:
    class_count = rng.randint(1, len(CLASS_NAMES))
    classes = CLASS_NAMES[:class_count]
    case_count = rng.randint(2, 5)
    cases = tuple(
        Case(
            generate_pattern(
                rng,
                classes,
                depth=4,
                capture_prefix=f"capture_{index}",
                allow_guard=True,
                allow_irrefutable=False,
            ),
            f"branch_{index}",
        )
        for index in range(case_count)
    )
    sample_values = []
    for case in cases:
        sample_values.append(case.pattern.matching_value())
        sample_values.append(case.pattern.nonmatching_value())
    sample_values.append("object()")
    default_body = "default" if rng.choice([True, False]) else None
    return Program(classes, "value", cases, default_body, tuple(sample_values))


def generate_pattern(
    rng: random.Random,
    classes: tuple[str, ...],
    *,
    depth: int,
    capture_prefix: str,
    allow_guard: bool,
    allow_irrefutable: bool,
) -> Pattern:
    if depth <= 0:
        return generate_leaf_pattern(
            rng, capture_prefix, allow_irrefutable=allow_irrefutable
        )
    choices = ["literal", "singleton", "class", "sequence", "or", "capture"]
    if not allow_irrefutable:
        choices.remove("capture")
    if allow_guard:
        choices.append("guard")
    if len(classes) > 1:
        choices.append("none-or-class")
    kind = rng.choice(choices)
    if kind == "literal":
        return LiteralPattern(rng.choice(LITERALS))
    if kind == "singleton":
        return SingletonPattern(rng.choice(SINGLETONS))
    if kind == "capture":
        return CapturePattern(capture_prefix)
    if kind == "none-or-class":
        return NoneTypeOrClassPattern(rng.choice(classes))
    if kind == "class":
        return generate_class_pattern(
            rng, classes, depth=depth, capture_prefix=capture_prefix
        )
    if kind == "sequence":
        return generate_sequence_pattern(
            rng, classes, depth=depth, capture_prefix=capture_prefix
        )
    if kind == "or":
        return generate_or_pattern(
            rng, classes, depth=depth, capture_prefix=capture_prefix
        )
    return GuardedPattern(
        generate_pattern(
            rng,
            classes,
            depth=depth - 1,
            capture_prefix=capture_prefix,
            allow_guard=False,
            allow_irrefutable=False,
        ),
        rng.choice(
            (
                "True",
                "not False",
                "hasattr({subject}, '__class__')",
                "not isinstance({subject}, dict)",
            )
        ),
    )


def generate_leaf_pattern(
    rng: random.Random, capture_prefix: str, *, allow_irrefutable: bool
) -> Pattern:
    kind = rng.choice(["literal", "singleton", "capture", "wildcard"])
    if not allow_irrefutable and kind in {"capture", "wildcard"}:
        kind = rng.choice(["literal", "singleton"])
    if kind == "literal":
        return LiteralPattern(rng.choice(LITERALS))
    if kind == "singleton":
        return SingletonPattern(rng.choice(SINGLETONS))
    if kind == "capture":
        return CapturePattern(capture_prefix)
    return WildcardPattern()


def generate_class_pattern(
    rng: random.Random, classes: tuple[str, ...], *, depth: int, capture_prefix: str
) -> ClassPattern:
    attrs = tuple(
        (
            attr,
            generate_pattern(
                rng,
                classes,
                depth=depth - 1,
                capture_prefix=f"{capture_prefix}_{attr}",
                allow_guard=False,
                allow_irrefutable=True,
            ),
        )
        for attr in rng.sample(ATTR_NAMES, rng.randint(0, 2))
    )
    return ClassPattern(rng.choice(classes), attrs)


def generate_sequence_pattern(
    rng: random.Random, classes: tuple[str, ...], *, depth: int, capture_prefix: str
) -> SequencePattern:
    length = rng.randint(1, 3)
    elements = tuple(
        generate_pattern(
            rng,
            classes,
            depth=depth - 1,
            capture_prefix=f"{capture_prefix}_{index}",
            allow_guard=False,
            allow_irrefutable=True,
        )
        for index in range(length)
    )
    return SequencePattern(
        elements,
        star=rng.choice([True, False]),
        tuple_value=rng.choice([True, False]),
    )


def generate_or_pattern(
    rng: random.Random, classes: tuple[str, ...], *, depth: int, capture_prefix: str
) -> OrPattern:
    if rng.choice([True, False]):
        alternatives: tuple[Pattern, ...] = tuple(
            LiteralPattern(value) for value in rng.sample(LITERALS, rng.randint(2, 4))
        )
        return OrPattern(alternatives)
    alternatives = tuple(
        generate_pattern(
            rng,
            classes,
            depth=depth - 1,
            capture_prefix=capture_prefix,
            allow_guard=False,
            allow_irrefutable=False,
        )
        for _ in range(rng.randint(2, 3))
    )
    # Python OR patterns require the same capture names in every alternative.
    if len({pattern.capture_names() for pattern in alternatives}) > 1:
        return OrPattern(
            tuple(LiteralPattern(value) for value in rng.sample(LITERALS, 2))
        )
    return OrPattern(alternatives)


def check_program(program: Program, style: IfStyle, *, seed: int) -> Issue | None:
    original = program.render_if_code(style, seed)
    match_reference = program.render_match_code()
    expected_trace = execute_result(match_reference)
    original_trace = execute_result(original)
    if original_trace != expected_trace:
        return Issue(
            kind="generator-bug",
            seed=-1,
            index=-1,
            style=style.value,
            original=original,
            converted=original,
            match_reference=match_reference,
            expected_trace=expected_trace,
            actual_trace=original_trace,
            changed=False,
            error="if renderer does not match match renderer",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "candidate.py"
        path.write_text(original, encoding="utf-8")
        converted_path, changed, error = convert_file(
            path,
            assumptions=Assumptions.from_names(),
        )
        converted = path.read_text(encoding="utf-8") if path.exists() else ""

    if converted_path != path:
        return Issue(
            kind="wrong-path",
            seed=-1,
            index=-1,
            style=style.value,
            original=original,
            converted=converted,
            match_reference=match_reference,
            expected_trace=expected_trace,
            actual_trace=("", "", None),
            changed=changed,
            error=f"converted_path={converted_path}",
        )
    if error is not None:
        return Issue(
            kind="convert-error",
            seed=-1,
            index=-1,
            style=style.value,
            original=original,
            converted=converted,
            match_reference=match_reference,
            expected_trace=expected_trace,
            actual_trace=("", "", None),
            changed=changed,
            error=error,
        )
    if not changed:
        return Issue(
            kind="not-converted",
            seed=-1,
            index=-1,
            style=style.value,
            original=original,
            converted=converted,
            match_reference=match_reference,
            expected_trace=expected_trace,
            actual_trace=original_trace,
            changed=False,
        )

    actual_trace = execute_result(converted)
    if actual_trace != expected_trace:
        return Issue(
            kind="trace-mismatch",
            seed=-1,
            index=-1,
            style=style.value,
            original=original,
            converted=converted,
            match_reference=match_reference,
            expected_trace=expected_trace,
            actual_trace=actual_trace,
            changed=changed,
        )
    return None


def issue_survives(source: str, style: IfStyle) -> bool:
    # Minimization only has original.py, so classify against itself by checking whether
    # Matchify still has a conversion problem. This intentionally skips not-converted
    # enhancement samples because they need the match reference for classification.
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        expected_trace = execute_result(source)
        _, changed, error = convert_file(path)
        converted = path.read_text(encoding="utf-8")
    if error is not None:
        return True
    return changed and execute_result(converted) != expected_trace


def minimize_source(source: str, *, enabled: bool, style: IfStyle) -> str:
    if not enabled:
        return source
    try:
        from pysource_minimize import minimize
    except ImportError as error:
        raise RuntimeError(
            "pysource-minimize is required. Install it or rerun with --no-minimize."
        ) from error
    return minimize(source, lambda candidate: issue_survives(candidate, style))


def make_sample_id(issue: Issue) -> str:
    digest = hashlib.sha256(issue.original.encode("utf-8")).hexdigest()[:12]
    return f"{issue.kind}-{issue.style}-seed-{issue.seed}-case-{issue.index}-{digest}"


def save_issue(issue: Issue, samples_dir: Path) -> Path:
    sample_dir = samples_dir / make_sample_id(issue)
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "original.py").write_text(issue.original, encoding="utf-8")
    (sample_dir / "converted.py").write_text(issue.converted, encoding="utf-8")
    (sample_dir / "trace.txt").write_text(issue.trace_text(), encoding="utf-8")
    (sample_dir / "match_reference.py").write_text(
        issue.match_reference, encoding="utf-8"
    )
    (sample_dir / "meta.json").write_text(
        json.dumps(
            {
                "kind": issue.kind,
                "seed": issue.seed,
                "index": issue.index,
                "style": issue.style,
                "changed": issue.changed,
                "error": issue.error,
                "expected": {
                    "output": issue.expected_trace[1],
                    "exception": exception_name(issue.expected_trace[2]),
                },
                "actual": {
                    "output": issue.actual_trace[1],
                    "exception": exception_name(issue.actual_trace[2]),
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return sample_dir


def find_issues(
    *,
    count: int,
    seed: int,
    style: IfStyle,
    samples_dir: Path,
    minimize: bool,
    stop_after: int,
    include_not_converted: bool,
) -> list[Path]:
    rng = random.Random(seed)
    saved = []
    for index in range(count):
        program = generate_program(rng)
        issue = check_program(program, style, seed=seed + index)
        if issue is None:
            continue
        if issue.kind == "not-converted" and not include_not_converted:
            continue
        issue = Issue(
            kind=issue.kind,
            seed=seed,
            index=index,
            style=style.value,
            original=issue.original,
            converted=issue.converted,
            match_reference=issue.match_reference,
            expected_trace=issue.expected_trace,
            actual_trace=issue.actual_trace,
            changed=issue.changed,
            error=issue.error,
        )
        if issue.kind in {"trace-mismatch", "convert-error"}:
            minimized = minimize_source(issue.original, enabled=minimize, style=style)
            if minimized != issue.original:
                minimized_issue = check_minimized_issue(minimized, issue)
                if minimized_issue is not None:
                    issue = minimized_issue
        sample_dir = save_issue(issue, samples_dir)
        print(f"saved {sample_dir}")
        saved.append(sample_dir)
        if len(saved) >= stop_after:
            break
    return saved


def check_minimized_issue(source: str, original_issue: Issue) -> Issue | None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "candidate.py"
        path.write_text(source, encoding="utf-8")
        expected_trace = execute_result(source)
        _, changed, error = convert_file(path)
        converted = path.read_text(encoding="utf-8")
    if error is None and (not changed or execute_result(converted) == expected_trace):
        return None
    return Issue(
        kind="convert-error" if error is not None else "trace-mismatch",
        seed=original_issue.seed,
        index=original_issue.index,
        style=original_issue.style,
        original=source,
        converted=converted,
        match_reference=source,
        expected_trace=expected_trace,
        actual_trace=("", "", None) if error is not None else execute_result(converted),
        changed=changed,
        error=error,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate match-representable if/elif programs and classify Matchify gaps."
    )
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260625)
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR)
    parser.add_argument("--stop-after", type=int, default=1)
    parser.add_argument(
        "--style",
        choices=[style.value for style in IfStyle],
        default=IfStyle.MIXED.value,
    )
    parser.add_argument(
        "--include-not-converted",
        action="store_true",
        help="Store match-representable inputs that Matchify currently leaves unchanged.",
    )
    parser.add_argument("--no-minimize", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    saved = find_issues(
        count=args.count,
        seed=args.seed,
        style=IfStyle(args.style),
        samples_dir=args.samples_dir,
        minimize=not args.no_minimize,
        stop_after=args.stop_after,
        include_not_converted=args.include_not_converted,
    )
    if not saved:
        print("no issues found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
