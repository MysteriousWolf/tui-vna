# TINA implementation plan

This document captures the agreed plan for the next feature work batch.
It is intentionally **not** a release note and should **not** be committed as part
of the product output. It is only a working design/implementation plan.

---

## Goals

The next batch should improve:

- export flexibility
- export metadata / recovery
- measurement note-taking
- tool usability
- recoverability through history and import

The work is grouped into **atomic functional units** so each unit can be
implemented, linted, tested, and committed independently.

---

## Implementation status

Completed so far:

- **Functional Unit 1 — Export templating core**
- **Functional Unit 2 — Setup output UI refresh**
- **Functional Unit 3 — CSV export**
- **Functional Unit 4 — Measurement tab layout with notes editor**
- **Functional Unit 5 — Human-readable notes block + machine-readable metadata block**
- **Functional Unit 6 — PNG/SVG embedded metadata and future recovery payload**
- **Functional Unit 7 — Import and recovery from measurement outputs**
- **Functional Unit 8 — Alt-modified minimal export mode**

Additional implementation notes:

- the original template-history dropdown idea was replaced by
  **autocomplete-based history/tag completion** for setup inputs
  (`host`, `port`, `filename`, `folder`)
- this keeps the same history/reuse goal while providing a faster input flow
- export bundle defaults UI is in place, while downstream exporter behavior for
  later formats remains part of later functional units
- Touchstone exports now include:
  - a readable raw-markdown notes block at the beginning
  - a trailing machine-readable YAML metadata block
- Touchstone import now has a metadata-aware path used by the app, while the
  legacy tuple-returning import helper remains for compatibility
- PNG and SVG exports now embed:
  - machine-readable YAML metadata
  - readable notes where practical
  - full raw measurement payload for future recovery
- image metadata writing is implemented for both direct exports and bundle
  exports; broader recovery/import from those outputs remains part of later
  functional units
- measurement-output import now restores Setup state from embedded metadata for:
  - `.s2p`
  - `.png`
  - `.svg`
- normal measurement import now restores:
  - Setup options
  - Measurement plot options
  - measurement notes
  - the active Measurement tab view
- image-based imports now reconstruct measurement data from embedded raw payloads
  when direct numeric trace data is not present in the source format
- a command-palette action now supports **Import setup from measurement output**
  for setup-only restoration without replacing the current loaded measurement
- minimal export mode is now available from the Measurement tab output controls
  via a dedicated toggle button
- minimal export mode omits notes/metadata payloads from:
  - Touchstone exports
  - PNG exports
  - SVG exports
  - bundle export outputs
- the minimal export toggle also updates export button styling so the active mode
  is visible before exporting

---

## Functional Unit 1 — Export templating core ✅ Done

### Goal

Replace the current prefix-oriented naming flow with a shared templating engine
used by both filename and output folder generation.

### Scope

Implement a reusable template system that:

- supports both filename and folder path fields
- preserves unknown tags literally
- validates unknown tags with a warning state
- validates invalid path characters with an error state
- supports direct strftime-style timestamp formatting inside braces

### Supported tags

Short tag names only:

- `{date}`
- `{time}`
- `{host}`
- `{vend}`
- `{model}`
- `{start}`
- `{stop}`
- `{span}`
- `{pts}`
- `{avg}`
- `{ifbw}`
- `{cal}`

In addition, any valid direct timestamp format in braces should be interpreted as
a timestamp formatter, for example:

- `{%Y%m%d_%H%M%S}`
- `{%Y-%m-%d}`
- `{%H%M}`

### Tag value rules

- frequency values use the unit selected in Setup
- units are **not** appended automatically
- boolean-like values should become human-readable lowercase text
  - example: `{cal}` -> `yes` / `no`

### Validation rules

- unknown tags remain literal in output
- unknown tags produce a **warning** state on the input
- invalid path characters produce an **error** state on the input
- export must refuse to proceed while path errors are present
- attempting export with errors should produce a toaster-style error notification

### Template history behavior

Each template field gets its **own** dropdown/history:

- filename template history
- folder template history

History behavior:

- simple MRU ordering by list position
- no saved "last used timestamp" field required
- when a measurement is triggered, the actually used template moves to the top
- if the same template already exists, do not duplicate it; move it to the top

---

## Functional Unit 2 — Setup output UI refresh ✅ Done

### Goal

Rework the Setup output area around the new template system and export bundle
options.

### Scope

Replace the current prefix/custom-filename-oriented setup flow with:

- filename template input
- filename template history autocomplete
- folder template input
- folder template history autocomplete
- export bundle checkboxes

### Export bundle options

Allow selecting default generated outputs:

- `s2p`
- `csv`
- `png`
- `svg`

### Help affordance

Add a clickable `?` action in the Output frame border title, matching the style
used by Tool Results help.

Clicking it should open a help page/modal explaining:

- supported template tags
- timestamp formatting syntax
- warning vs error states
- a few concrete examples

### Open behavior decision already resolved

- unknown tags: warning only
- invalid path chars: hard error
- same templating system must work for both filename and folder

---

## Functional Unit 3 — CSV export ✅ Done

### Goal

Add CSV export to the existing export pipeline.

### Scope

Implement CSV export for the current measurement alongside existing output types.

### UI location

Measurement tab output actions and export bundle flow.

### Behavior

- export current measurement traces in a simple tabular format
- use selected measurement data and trace/export choices already present in app state
- participate in the same filename/folder templating system
- participate in the export bundle choices

### Metadata policy for CSV

CSV stays intentionally minimal:

- no full embedded machine-readable metadata block
- optional small human-readable header area is acceptable only if unobtrusive

### Notes

Do not overcomplicate CSV with recovery payloads in this phase.

---

## Functional Unit 4 — Measurement tab layout with notes editor ✅ Done

### Goal

Add measurement notes without bloating the tab and keep plot options usable.

### Scope

Rework the Measurement tab controls row so options and notes share the same area.

### Layout

Split the row approximately:

- `2/3` options area
- `1/3` notes area

### Options area layout

Preserve a four-row structure:

1. type + show selector row
2. X axis controls row
3. Y axis controls row
4. apply/reset action row

### Notes editor behavior

- provide a markdown-oriented editor for measurement notes
- notes remain stored/exported as **raw markdown**
- no export-time markdown rendering

### Preview / highlighting behavior

Preferred behavior:

- left half of notes area: editor
- right half of notes area: live sample preview
- generated / interpreted parts in preview should be visually highlighted in the
  same color family as the source text highlighting if feasible

Fallback behavior:

- if syntax highlighting inside the editor is not practical/clean,
  keep highlighting only in the preview/sample pane

### Important constraint

Even if a live preview exists, exported note text must remain raw markdown only.

---

## Functional Unit 5 — Human-readable notes block + machine-readable metadata block ✅ Done

### Goal

Make exports re-importable and self-describing without cluttering the primary data.

### Scope

Add two distinct metadata layers:

1. **Readable notes block at the beginning**
2. **Machine-readable settings block at the end**

### Readable notes block

Location:

- beginning of export file where comment syntax supports it

Contents:

- raw markdown notes only
- intended for humans
- may include a short explanatory line if useful

### Machine-readable settings block

Location:

- trailing block at end of export file

Format:

- plain YAML preferred
- include a metadata/settings version field for future migrations

### Machine-readable settings content

Should include:

- everything on the Setup page
- measurement plot options
- enough information to restore setup and measurement display state
- in formats where appropriate, additional measurement data for future recovery

### S2P-specific rule

For `.s2p`:

- notes block at the beginning
- machine settings block at the end
- do **not** redundantly re-store data already explicitly present in the Touchstone
  body/header where unnecessary
- plain YAML-in-comments is preferred over encoded payloads

### User guidance comment

Near the machine block, include a clear note that:

- markdown notes may be edited manually
- machine settings should not be manually changed if reliable re-import is desired

### Metadata versioning

A version field is mandatory so later migrations/updaters can be introduced safely.

---

## Functional Unit 6 — PNG/SVG embedded metadata and future recovery payload ✅ Done

### Goal

Carry export metadata beyond text formats and enable future file-only recovery.

### Scope

Embed metadata into generated PNG and SVG outputs.

### PNG

Use standard metadata support available in the image format/tooling.

### SVG

Use embedded comment/metadata-compatible approach in SVG.

### Embedded content

Store:

- same machine-readable YAML metadata as other importable formats
- readable notes where practical
- full raw measurement data payload in YAML as agreed, even if redundant in size,
  since it should be negligible compared to image size for PNG and useful for
  future import/recovery workflows

### Import intent

This unit is primarily about writing the metadata cleanly so future file import
can reconstruct measurement content even if sibling exports are lost.

---

## Functional Unit 7 — Import and recovery from measurement outputs ✅ Done

### Goal

Allow old measurement outputs to restore app state directly.

### Scope

Support two recovery behaviors:

1. normal measurement import
2. setup-only import via command palette

### Normal measurement import

When importing from a supported measurement output:

- restore Setup options
- restore Measurement plot options
- show the Measurement tab

### Setup-only import

Add a command palette action:

- **Import setup from measurement output**

This should:

- read embedded metadata/settings
- restore Setup page only

### Overwrite rule

Import should overwrite current unsaved setup/options directly.

### File support target

At minimum:

- `.s2p` metadata import

Follow-on if practical within same unit:

- PNG/SVG metadata import for setup restoration
- future full measurement reconstruction if embedded data is available

---

## Functional Unit 8 — Alt-modified minimal export mode ✅ Done

### Goal

Provide a quick way to create clean output files without notes/metadata payloads.

### Scope

For all export actions and bundle exports:

- holding `Alt` while clicking should generate minimized outputs
- minimized outputs omit metadata/comment payloads

### Applies to

- all individual export buttons
- bundle export flow

### Notes

This depends on reliable modifier handling in the runtime event model.
If needed, implementation can be adjusted later, but the intended UX is clear.

---

## Functional Unit 9 — Reusable frequency-entry component ✅ Done

### Goal

Reduce duplicated tool frequency input logic and prepare for extrema navigation.

### Scope

Create a reusable frequency-entry widget/component for tool controls.

### Component responsibilities

- frequency input
- previous extrema button
- next extrema button
- consistent validation/parsing behavior for tool frequencies

### Usage target

All frequency-entry style fields in the Tools tab should migrate to this widget.

### Status

Implementation completed. The reusable frequency-entry component and its extrema navigation hooks were implemented and integrated into the Tools tab. While implementing this unit a small set of robustness fixes were added to export/import handlers (to tolerate missing widgets when running headless tests), and test-suite regressions triggered by these flows were resolved. All unit tests pass locally after these changes and the implementation is marked done.

---

## Functional Unit 10 — Extrema navigation in tools

### Goal

Improve cursor placement and tool workflow without adding a separate peak-finder tool.

### Scope

Build extrema navigation into the reusable frequency-entry component.

### Search scope

- visible plot range only

### Default behavior

- strict local maxima

### Modifier behavior target

- `Alt`: minima mode
- `Ctrl`: smoothed-search mode

### Smoothed-search mode

Preferred approach:

- use an SG-like smoothing fit
- detect candidate extremum on smoothed curve
- snap to nearest meaningful extremum on the original raw curve

### Implementation fallback

First attempt:

- implement real modifier-based button behavior

If that turns out not to be clean/reliable enough:

- add explicit extra controls instead:
  - extrema type toggle
  - smoothing toggle

### Visual feedback

If minima mode or smoothing mode is active, the UI should make that obvious.

---

## Functional Unit 11 — Copy full tool results

### Goal

Make tool outputs easy to reuse elsewhere without manual selection.

### Scope

Add a copy action to the Tools results panel title area, next to the existing `?`.

### Behavior

Copy the full current tool results as a clean plain-text/table block.

### Applies to

- cursor tool
- distortion tool
- future tools added later

### UI consistency

This should mirror the lightweight copy affordance already used on the Log tab.

---

## Functional Unit 12 — Persistent command-palette history

### Goal

Add recovery and recent-file workflows without adding always-visible UI clutter.

### Scope

Implement persistent history-based command palette actions.

### History types

Keep up to the last `10` entries for:

- setup/session recovery history
- recently exported measurements
- recently imported measurements

### Stored data

Each entry stores:

- path
- label

### Missing-file behavior

If a selected history item points to a path that no longer exists:

- warn that the file has moved / is missing
- remove that entry from history

### Command palette actions

Implement as **separate commands**:

- restore setup/session
- open recent measurement
- import setup from measurement output

Do not collapse these into one generic command.

---

## Functional Unit 13 — Save-back workflow

### Goal

Persist note/metadata changes back into the original source measurement file.

### Scope

Implement `Ctrl+S` behavior for applicable measurement files.

### Behavior

When working from an importable/original measurement output file:

- save notes and metadata back into that original file where supported

Additionally:

- save current app settings/setup template history if needed
- if the resulting setup/template state differs from all previously stored entries,
  persist it into the appropriate history structures

### Primary target

- original `.s2p` created by the application

### Notes

This is specifically about metadata/notes persistence, not a generic "save all app state"
command.

---

## Cross-cutting implementation notes

### Validation styling

Need distinct visual states for:

- normal
- warning
- error

Target use cases:

- unknown template tags -> warning
- invalid path characters -> error

### Export context model

It will likely help to define a single export context object/dict used by:

- template rendering
- export naming
- machine-readable metadata generation
- notes block generation

### Metadata schema

Define one schema versioned from day one.
This schema should be the same one used for:

- trailing export metadata
- setup import from measurement output
- history/session restore where appropriate

### Recovery philosophy

The app should increasingly treat exported files as potential recovery sources, not
just one-way outputs.

---

## Suggested implementation order

Recommended sequence:

1. **Export templating core**
2. **Setup output UI refresh**
3. **CSV export**
4. **Measurement notes UI**
5. **Readable notes + machine metadata blocks**
6. **Import/recovery from measurement outputs**
7. **PNG/SVG metadata embedding**
8. **Reusable frequency-entry component**
9. **Extrema navigation**
10. **Copy full tool results**
11. **Persistent command-palette history**
12. **Save-back workflow**
13. **Alt-modified minimal export mode**

This order keeps dependencies mostly aligned:

- templating before export consumers
- metadata schema before recovery flows
- frequency widget before extrema UX
- history before advanced restore flows can feel complete

---

## Final notes

This plan intentionally leaves room for implementation discoveries, especially around:

- runtime modifier handling in Textual
- editor highlighting feasibility
- image metadata ergonomics
- re-import edge cases

However, the product decisions in this document should be treated as the current
design baseline for the feature batch.
