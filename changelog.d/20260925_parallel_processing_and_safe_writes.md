## Changed

- Improved performance on large source trees for previews, interactive runs,
  and writes. Parallel results are now reported as files finish processing.
  ([#30](https://github.com/15r10nk/matchify/pull/30))

## Fixed

- Ctrl-C now stops parallel workers cleanly, including during startup, without
  hanging or printing worker tracebacks, and exits with status 130.
  ([#30](https://github.com/15r10nk/matchify/pull/30))
- Preserve the original source text when no conversions are selected.
  ([#30](https://github.com/15r10nk/matchify/pull/30))
- Write converted source files atomically so interruption cannot leave a
  partially written source file. Writes respect read-only permissions, retain
  symlinks and supported file metadata, and support maximum-length filenames.
  ([#31](https://github.com/15r10nk/matchify/pull/31))
- Reject negative `--jobs` values instead of silently skipping files and
  returning success. `--jobs 0` continues to select the CPU count automatically.
  ([#31](https://github.com/15r10nk/matchify/pull/31))
