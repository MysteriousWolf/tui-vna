# Changelog

All notable changes to this project will be documented in this file.

## v0.3.0 - 2026-05-08

### Highlights
- Improved extrema-detection pipeline: SciPy savgol + median filter +
  find_peaks with a NumPy fallback.
- Short-lived extrema detection cache keyed by data buffer and options.
- Tools: frequency-entry component with previous/next extrema navigation.
- UX: importing a measurement no longer auto-switches the active tab.
- Removed demo/sandbox script and related .zed task entry.
- Lint/style sweep (black + ruff fixes) and test updates.
- Fix: save-back always reported "no file available" when a touchstone
  path was set; bare else: in the PNG/SVG fallback chain fired even when
  the s2p payload was already built.
- Tool selector buttons now span full width with equal dynamic allocation
  and a 1-char separator between buttons.
- GUI mixin scaffolding (GUIAppTypingMixin protocol + per-concern shims).
- Typing improvements across autocomplete, update notification, and
  command palette components; set_class() argument order fixed.
- Tests for config migration module.

### Completed Units
- Units done: 1 (templating), 2 (setup output UI), 3 (CSV export),
  4 (measurement notes UI), 5 (notes + metadata), 6 (PNG/SVG metadata),
  7 (import/recovery), 8 (alt minimal export), 9 (frequency-entry),
  10 (extrema navigation in tools), 11 (copy full tool results),
  12 (persistent command-palette history), 13 (save-back workflow).

### Pending / Deferred
- Extrema search on the Measurement tab was intentionally skipped for
  stability reasons (TUI modifier handling issues).

### Release Prep Checklist
- [x] Update README requirements (note SciPy dependency)
- [x] Document the no-tab-switch import UX in README
- [x] Bump version and tag release
- [x] Ensure CI runs the same lint/test commands
- [x] Add unit tests for extrema cache and SciPy/NumPy fallback
- [ ] Verify PyInstaller binary builds (optional)

## Previous releases
- (none yet)
