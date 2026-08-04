# Changelog

<!-- scriv-insert-here -->

<a id='changelog-0.1.0'></a>
# 0.1.0 — 2026-08-04

## Added

- Added `--check` mode. It reports files that would be converted without
  modifying them and exits with status 1 when changes are needed or processing
  errors occur.
- Added `matchify` and `matchify-check` pre-commit hooks for automatic rewriting
  and check-only CI workflows.
- Added conversion of eligible inline dictionary lookups and single-use local
  lookup-table variables into `match` statements. Literal and nested tuple keys,
  arbitrary value expressions, comments, single evaluation of the lookup key,
  and the original `KeyError` behavior are preserved where supported. This
  conversion requires the new `lookup-equality` assumption.
- Added the `identity-equality` assumption, allowing qualified identity checks
  such as `value is Enum.MEMBER` to become value patterns when identity and
  equality are known to be equivalent.
- Added separate `list-sequence-pattern` and `tuple-sequence-pattern`
  assumptions for converting explicit sequence type checks into Python sequence
  patterns. Checks against both types require both assumptions.
- Exported `Assumptions` from the top-level `matchify` package.
- Added an MIT license.

## Changed

- Composite match subjects selected under `pure-subjects` now use paths shared
  by a majority of branches. This enables more eligible mixed-subject chains to
  be converted while keeping less common checks in guards.
- Sequence transformations are more conservative: an `isinstance` check for
  `list` or `tuple` is no longer treated as implied by a sequence pattern unless
  the corresponding assumption is enabled. Qualified class names remain
  guarded and are not covered by these assumptions.
- CLI summaries distinguish check results with `would convert`, and normal as
  well as check mode now return a failure status for processing errors.
- Release automation now uses dedicated release pull requests, tags the tested
  merge commit, publishes it to PyPI, and creates GitHub release notes from
  Scriv fragments.

## Fixed

- Preserved comments attached to dictionary lookup statements during
  conversion.
- Restricted dictionary lookup conversion to safe, unambiguous candidates.
  Chained subscriptions, reused local tables, multiple or unsupported uses,
  duplicate or unhashable keys, dictionary unpacking, and other unsafe forms
  remain unchanged.
- Avoided capture-name collisions in generated missing-key cases.

## Development

- Expanded behavior and public-API tests, including generated runtime
  round-trips, and enforced 100% branch coverage.
- Added locked dependencies, lowest-direct-dependency CI coverage, PyPy 3.11
  testing, and updated repository template and maintenance automation.
