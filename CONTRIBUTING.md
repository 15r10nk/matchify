# Contributing
Contributions are welcome.
Please create an issue before writing a pull request so we can discuss what needs to be changed.

# Testing
The code can be tested with [hatch](https://hatch.pypa.io/latest/)

* `hatch run cov:test` can be used to test all supported python versions and to check for coverage.
* `hatch run +py=3.10 all:test -- --sw` runs pytest for python 3.10 with the `--sw` argument.

## Testing against external repositories

`test-repos.py` clones the projects configured in `test-repos.json`, prepares
their test environments, runs a baseline test suite, applies the local Matchify
checkout, validates changed files with the project's Python interpreter, and
reruns the tests.

Run one configured repository:

```bash
uv run python test-repos.py django-rest-framework \
  --workspace /tmp/matchify-drf
```

Run every configured repository or list the available names:

```bash
uv run python test-repos.py --workspace /tmp/matchify-repos
uv run python test-repos.py --list
```

The workspace must be new. Each repository gets isolated clone, setup, test,
Matchify, and syntax logs. A combined `summary.json` is written at the
workspace root. Use `--skip-baseline` to omit the initial test run or
`--skip-tests` to perform setup, conversion, and syntax validation only.

Repository entries may configure `url`, `ref`, clone arguments, source and
excluded paths, extra Matchify arguments, setup commands, the target Python
command, the test command, environment variables, batch size, and timeout. The
`{root}`, `{repo}`, and `{workspace}` placeholders are available in commands and
environment values.

# Commits
Please use [pre-commit](https://pre-commit.com/) for your commits.

# Changelog
Add a changelog fragment for user-visible changes with
`uv run scriv create --add --edit`. The fragments are collected automatically
when the release pull request is created.
