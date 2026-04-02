The **Output** section controls:

- **Filename** — the exported file name
- **Folder** — where exports are written

Both fields use the same template syntax.

Unknown tags stay literal and show a warning.

Invalid path characters show an error and block export.

## Supported tags

`{date}` `{time}` `{host}` `{vend}` `{model}` `{start}` `{stop}` `{span}` `{pts}` `{avg}` `{ifbw}` `{cal}`

## Time formatting

You can also put a direct time format inside braces:

`{%Y%m%d_%H%M%S}` ` {%Y-%m-%d}` ` {%H%M}`

These use the current local time at export.

## Value rules

- Frequency values use the unit selected in **Setup**
- Units are not added automatically
- Boolean-style values render as lowercase text

Example: `{cal}` → `yes` / `no`

## Validation

**Warning:** unknown tags are allowed and remain unchanged.

Example: template `measurement_{unknown}_{date}` → result `measurement_{unknown}_2025-01-31`

**Error:** invalid path characters are not allowed.

Examples: `< > : " | ? *`

## Examples

Filename: `measurement_{date}_{time}` → `measurement_2025-01-31_142530`

Folder: `exports/{vend}_{model}` → `exports/keysight_E5071B`

Filename: `{host}_{start}_{stop}_{pts}pt` → `192.168.1.50_1_1100_601pt`

Filename: `run_{%Y%m%d_%H%M%S}` → `run_20250131_142530`

## History

Filename and folder histories are stored separately.

Reusing a template moves it to the top of history without duplicating it.
