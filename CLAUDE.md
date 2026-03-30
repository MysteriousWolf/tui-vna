# Claude Code Guidelines — tina (tui-vna)

## Project Overview

Python TUI application built on [Textual](https://textual.textualize.io/).
Primary source: `src/tina/main.py` (large single-file app with Textual widgets,
event handlers, and async plot rendering). Plugin-style VNA drivers live in
`src/tina/drivers/`. Tool computations (cursor, measure, distortion) are in
`src/tina/tools/`.

Package manager: **uv**. Python ≥ 3.10.

---

## Workflow

### 1. Verify Before Touching

For every requested change, read the relevant code first and confirm the issue
actually exists in the current state. If it is already correct or was already
fixed, skip it and say why — do not apply redundant edits.

### 2. Functional Grouping

Partition the requested changes into **Atomic Functional Units** before starting.
A functional unit is a coherent, independently testable slice of work. Examples
for this project:

| Unit type | Examples |
|---|---|
| Defensive guard | Cursor out-of-bounds checks across both plot backends |
| UI/visual fix | Theme refresh handler, resize debounce visibility gate |
| Code quality | Docstring coverage pass, lint clean-up |
| New feature | New tool, new driver, new TUI widget |
| Refactor | Extracting a helper method, renaming, reorganising |

Cross-cutting changes that touch the same logical concern (e.g. the same bug in
two plot backends) belong in **one** unit, not two.

### 3. Fix → Lint → Commit Cycle

Process one unit at a time:

1. **Apply** the fix using existing project APIs where possible (prefer calling
   `_refresh_*` helpers or `call_after_refresh` over inline plot code).
2. **Lint** — run the project lint script and fix any issues it raises:
   ```bash
   ./scripts/lint.sh --fix
   ```
3. **Commit** — commit before moving to the next unit.

Never batch multiple functional units into a single commit.

### 4. Commit Message Convention

Capital imperative verb followed by a short description, no punctuation between
them, ≤ 72 chars. The verb itself signals intent — no separate type keyword.

```text
<Verb> <description>
```

Common verbs and when to use them:

| Verb | When to use |
|---|---|
| `Fix` | Bug fix, wrong behaviour, crash |
| `Add` | New capability, file, dependency |
| `Implement` | Larger new feature built from scratch |
| `Improve` | Enhancement to something that already works |
| `Address` | Response to review comments |
| `Bump` | Version or dependency update |
| `Remove` | Deleting something |

Examples:
```text
Fix cursor overlays rendering outside sweep range
Add measurement refresh on theme change
Improve tools plot resize debounce with tab visibility check
Add docstrings to reach coverage threshold
Fix lint issues
Improve project structure
```

---

## Toolchain

| Tool | Purpose | Command |
|---|---|---|
| `black` | Code formatter | `./scripts/lint.sh --fix` |
| `ruff` | Linter | `./scripts/lint.sh --fix` |
| `pytest` | Tests | `./scripts/test.sh` |
| `uv` | Package / venv manager | — |

Always run `./scripts/lint.sh --fix` after edits and before committing.
The CI enforces both black formatting and ruff rules.

---

## Project-Specific Patterns

- **Plot rendering** is split across two backends: `terminal` (Plotext) and
  `image` (matplotlib). Any fix to plot overlay logic must be applied to **both**
  backends.
- **Theme-sensitive** re-renders go through `call_after_refresh(self._refresh_*)`
  — never redraw synchronously inside an event handler.
- **Resize debounce** uses `set_timer` + stored timer handles. Gate tools-tab
  redraws behind a tab-visibility check.
- **`last_measurement`** is the single source of truth for cached measurement
  data. All refresh helpers read from it; do not pass raw arrays directly.
- **Tool computations** (`src/tina/tools/`) must validate cursor positions against
  `freqs[0]`/`freqs[-1]` before interpolating — `np.interp` silently extrapolates.
