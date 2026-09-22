### Added

- Added `--convert-if EXPRESSION` to select eligible `if`/`elif` conversions
  using source and generated-pattern metrics, for example
  `--convert-if "branches >= 4 and guard_conditions == 0"`. The default is
  `True`, which selects every eligible chain. Dictionary lookup conversions
  are unaffected by this filter.
- Conversion previews now display metrics for use in `--convert-if`
  expressions, including branch, pattern, guard, capture, and qualified-value
  counts.
