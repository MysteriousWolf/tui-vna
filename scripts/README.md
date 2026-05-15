# Build Scripts

Creates standalone executables for TINA.

## Local Build

```bash
# Windows
scripts/build.bat

# Linux/macOS
source ./scripts/build.sh

# Fish shell
source ./scripts/build.fish
```

**Output:** `dist/tina(.exe)` + `dist/tina-quick(.exe)`

## What's Built

- **`tina`** — Full TUI application
- **`tina-quick`** — CLI-only quick measurement tool (runs `--now`)

## CI Builds

Release binaries are built automatically by GitHub Actions on every tagged release. See [RELEASE.md](../RELEASE.md) for the release process.

## Troubleshooting

**Build fails:** Ensure uv is installed and `uv sync --group dev` has been run  
**Won't run:** Check antivirus, architecture compatibility (64-bit)  
**Clean:** `rm -rf ../build ../dist` then rebuild
