# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Highlights
- Improved extrema-detection pipeline: SciPy savgol + median filter +
  find_peaks with a NumPy fallback.
- Short-lived extrema detection cache keyed by data buffer and options.
- Tools: frequency-entry component with previous/next extrema navigation.
- UX: importing a measurement no longer auto-switches the active tab.
- Removed demo/sandbox script and related .zed task entry.
- Lint/style sweep (black + ruff fixes) and test updates.

### Completed Units
- Units done: 1 (templating), 2 (setup output UI), 3 (CSV export)
  4 (measurement notes UI), 5 (notes + metadata), 6 (PNG/SVG metadata),
  7 (import/recovery), 8 (alt minimal export), 9 (frequency-entry),
  10 (extrema navigation in tools).

### Pending / Deferred
- Unit 11: explicit "Copy full tool results" action — per-cell clickable
  copy affordances exist, but the Results-panel title copy button is not
  implemented.
- Units 12–13: persistent command-palette history and save-back workflow.
- Extrema search on the Measurement tab was intentionally skipped for
  stability reasons (TUI modifier handling issues).

### Release Prep Checklist
- [ ] Update README requirements (note SciPy dependency)
- [ ] Document the no-tab-switch import UX in README
- [ ] Bump version and tag release
- [ ] Ensure CI runs the same lint/test commands
- [ ] Add unit tests for extrema cache and SciPy/NumPy fallback
- [ ] Verify PyInstaller binary builds (optional)

## Previous releases
- (none yet)
