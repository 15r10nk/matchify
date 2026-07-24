#!/usr/bin/env python3
"""Clone configured repositories, apply Matchify, and compare their test suites."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "test-repos.json"
SUMMARY_RE = re.compile(
    r"Summary: (?P<changed>\d+) converted, "
    r"(?P<unchanged>\d+) unchanged, (?P<errors>\d+) errors"
)


@dataclass
class CommandResult:
    command: list[str]
    returncode: int | None
    seconds: float
    log: str
    timed_out: bool = False


@dataclass
class RepoResult:
    name: str
    url: str
    revision: str | None = None
    status: str = "not_started"
    setup: list[CommandResult] = field(default_factory=list)
    baseline: CommandResult | None = None
    matchify: CommandResult | None = None
    matchify_reported_errors: int = 0
    files_scanned: int = 0
    changed_files: list[str] = field(default_factory=list)
    syntax_check: CommandResult | None = None
    post_conversion: CommandResult | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repos", nargs="*", help="Repository names from the JSON file")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("/tmp/matchify-repos"),
        help="Fresh directory for clones and logs; it must not already exist",
    )
    parser.add_argument(
        "--list", action="store_true", help="List configured repositories"
    )
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    return parser.parse_args()


def load_config(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        config = json.load(stream)
    if not isinstance(config, dict) or not config:
        raise ValueError("configuration must be a non-empty JSON object")
    required = {"url", "paths", "test_command"}
    for name, repo in config.items():
        if not isinstance(repo, dict):
            raise ValueError(f"{name}: configuration must be an object")
        missing = required - repo.keys()
        if missing:
            raise ValueError(f"{name}: missing fields: {', '.join(sorted(missing))}")
        for key in (
            "paths",
            "exclude_paths",
            "clone_args",
            "matchify_args",
            "test_command",
            "python_command",
        ):
            if key in repo and not isinstance(repo[key], list):
                raise ValueError(f"{name}.{key}: expected an array")
        if not all(
            isinstance(command, list) for command in repo.get("setup_commands", [])
        ):
            raise ValueError(f"{name}.setup_commands: expected an array of arrays")
    return config


def expand(items: Sequence[str], values: dict[str, str]) -> list[str]:
    return [item.format_map(values) for item in items]


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    timeout: int,
) -> CommandResult:
    started = time.monotonic()
    timed_out = False
    returncode: int | None
    with log.open("w", encoding="utf-8") as stream:
        stream.write(f"$ {shlex.join(command)}\n\n")
        stream.flush()
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            returncode = completed.returncode
        except subprocess.TimeoutExpired:
            returncode = None
            timed_out = True
            stream.write(f"\nTimed out after {timeout} seconds.\n")
    return CommandResult(
        command=list(command),
        returncode=returncode,
        seconds=round(time.monotonic() - started, 3),
        log=str(log),
        timed_out=timed_out,
    )


def iter_python_files(repo: Path, config: dict[str, Any]) -> list[Path]:
    excluded = tuple(repo / path for path in config.get("exclude_paths", []))
    files: list[Path] = []
    for configured_path in config["paths"]:
        root = repo / configured_path
        candidates = (root,) if root.is_file() else root.rglob("*.py")
        files.extend(
            path
            for path in candidates
            if path.suffix == ".py"
            and not any(path == prefix or prefix in path.parents for prefix in excluded)
        )
    return sorted(set(files))


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_matchify(
    files: Sequence[Path],
    *,
    repo: Path,
    args: Sequence[str],
    env: dict[str, str],
    log: Path,
    timeout: int,
    batch_size: int,
) -> tuple[CommandResult, int]:
    started = time.monotonic()
    returncode: int | None = 0
    timed_out = False
    reported_errors = 0
    display_command = [sys.executable, "-m", "matchify", *args, "<python files>"]

    with log.open("w", encoding="utf-8") as stream:
        for start in range(0, len(files), batch_size):
            relative_files = [
                str(path.relative_to(repo))
                for path in files[start : start + batch_size]
            ]
            command = [sys.executable, "-m", "matchify", *args, *relative_files]
            stream.write(f"$ {shlex.join(command)}\n")
            stream.flush()
            try:
                completed = subprocess.run(
                    command,
                    cwd=repo,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                stream.write(f"Timed out after {timeout} seconds.\n")
                returncode = None
                timed_out = True
                break
            stream.write(completed.stdout)
            if completed.returncode != 0:
                returncode = completed.returncode
            for match in SUMMARY_RE.finditer(completed.stdout):
                reported_errors += int(match.group("errors"))

    result = CommandResult(
        command=display_command,
        returncode=returncode,
        seconds=round(time.monotonic() - started, 3),
        log=str(log),
        timed_out=timed_out,
    )
    return result, reported_errors


def syntax_check(
    files: Sequence[str],
    *,
    python_command: Sequence[str],
    repo: Path,
    env: dict[str, str],
    log: Path,
    timeout: int,
) -> CommandResult:
    checker = (
        "import pathlib,sys\n"
        "failed = False\n"
        "for name in sys.argv[1:]:\n"
        "    try:\n"
        "        compile(pathlib.Path(name).read_bytes(), name, 'exec')\n"
        "    except (SyntaxError, ValueError) as error:\n"
        "        failed = True\n"
        "        print(f'{name}: {type(error).__name__}: {error}')\n"
        "raise SystemExit(failed)\n"
    )
    command = [*python_command, "-c", checker, *files]
    return run_command(command, cwd=repo, env=env, log=log, timeout=timeout)


def run_repo(
    name: str,
    config: dict[str, Any],
    *,
    workspace: Path,
    skip_baseline: bool,
    skip_tests: bool,
) -> RepoResult:
    run_root = workspace / name
    repo = run_root / "repo"
    logs = run_root / "logs"
    logs.mkdir(parents=True)
    timeout = int(config.get("timeout", 3600))
    values = {
        "repo": str(repo),
        "workspace": str(run_root),
        "root": str(ROOT),
    }
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["PYTHONPATH"] = str(ROOT / "src")
    for key, value in config.get("environment", {}).items():
        env[key] = value.format_map(values)

    result = RepoResult(name=name, url=config["url"])
    clone_command = [
        "git",
        "clone",
        *config.get("clone_args", ["--depth", "1"]),
    ]
    if revision := config.get("ref"):
        clone_command.extend(("--branch", revision))
    clone_command.extend((config["url"], str(repo)))
    clone = run_command(
        clone_command,
        cwd=run_root,
        env=env,
        log=logs / "clone.log",
        timeout=timeout,
    )
    result.setup.append(clone)
    if clone.returncode != 0:
        result.status = "clone_failed"
        return result

    revision_result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    result.revision = revision_result.stdout.strip()

    for index, configured_command in enumerate(config.get("setup_commands", []), 1):
        command = expand(configured_command, values)
        setup = run_command(
            command,
            cwd=repo,
            env=env,
            log=logs / f"setup-{index}.log",
            timeout=timeout,
        )
        result.setup.append(setup)
        if setup.returncode != 0:
            result.status = "setup_failed"
            return result

    if not skip_tests and not skip_baseline:
        result.baseline = run_command(
            expand(config["test_command"], values),
            cwd=repo,
            env=env,
            log=logs / "baseline.log",
            timeout=timeout,
        )

    files = iter_python_files(repo, config)
    result.files_scanned = len(files)
    before = {path: file_digest(path) for path in files}
    result.matchify, result.matchify_reported_errors = run_matchify(
        files,
        repo=repo,
        args=config.get("matchify_args", []),
        env=env,
        log=logs / "matchify.log",
        timeout=timeout,
        batch_size=int(config.get("batch_size", 250)),
    )
    result.changed_files = [
        str(path.relative_to(repo))
        for path, digest in before.items()
        if path.exists() and file_digest(path) != digest
    ]

    python_command = expand(
        config.get("python_command", [sys.executable]),
        values,
    )
    result.syntax_check = syntax_check(
        result.changed_files,
        python_command=python_command,
        repo=repo,
        env=env,
        log=logs / "syntax.log",
        timeout=timeout,
    )

    if not skip_tests:
        result.post_conversion = run_command(
            expand(config["test_command"], values),
            cwd=repo,
            env=env,
            log=logs / "post-conversion.log",
            timeout=timeout,
        )

    if result.matchify.returncode != 0 or result.matchify_reported_errors:
        result.status = "matchify_failed"
    elif result.syntax_check.returncode != 0:
        result.status = "invalid_generated_syntax"
    elif result.post_conversion and result.post_conversion.returncode != 0:
        result.status = "post_conversion_tests_failed"
    elif result.baseline and result.baseline.returncode != 0:
        result.status = "baseline_tests_failed"
    else:
        result.status = "passed"
    return result


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Invalid configuration: {error}", file=sys.stderr)
        return 2

    if args.list:
        for name in config:
            print(name)
        return 0

    selected = args.repos or list(config)
    unknown = sorted(set(selected) - config.keys())
    if unknown:
        print(f"Unknown repositories: {', '.join(unknown)}", file=sys.stderr)
        return 2

    workspace = args.workspace.resolve()
    if workspace.exists():
        print(f"Refusing to reuse existing workspace: {workspace}", file=sys.stderr)
        return 2
    workspace.mkdir(parents=True)

    results = []
    for name in selected:
        print(f"==> {name}", flush=True)
        result = run_repo(
            name,
            config[name],
            workspace=workspace,
            skip_baseline=args.skip_baseline,
            skip_tests=args.skip_tests,
        )
        results.append(result)
        print(
            f"    {result.status}: "
            f"{len(result.changed_files)}/{result.files_scanned} files changed",
            flush=True,
        )

    summary = workspace / "summary.json"
    summary.write_text(
        json.dumps([asdict(result) for result in results], indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Summary: {summary}")
    return 0 if all(result.status == "passed" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
