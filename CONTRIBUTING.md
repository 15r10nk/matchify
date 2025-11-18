# Contributing
Contributions are welcome.
Please create an issue before writing a pull request so we can discuss what needs to be changed.

# Testing
The code can be tested with [hatch](https://hatch.pypa.io/latest/)

* `hatch run cov:test` can be used to test all supported python versions and to check for coverage.
* `hatch run +py=3.10 all:test -- --sw` runs pytest for python 3.10 with the `--sw` argument.



# Commits
Please use [pre-commit](https://pre-commit.com/) for your commits.
