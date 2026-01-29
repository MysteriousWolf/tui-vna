# Build Scripts

Creates standalone executables for the HP E5071B VNA Control Tool.

## Quick Start

```bash
# Windows
scripts/build.bat

# Linux/macOS
source ./scripts/build.sh

# Fish shell
source ./scripts/build.fish
```

**Output:** `dist/hp-e5071b(.exe)` + `dist/hp-e5071b-quick(.exe)`

## What's Built

- **`hp-e5071b`** - Main GUI application with full interface
- **`hp-e5071b-quick`** - Double-click quick measurement tool (runs `--now`)

## Distribution

**Standalone executables** - no Python or dependencies required.

**Windows:** Distribute both `.exe` files for full control + quick measurements  
**Linux/macOS:** Users typically prefer `uv tool install` for easier updates

## Troubleshooting

**Build fails:** Ensure you're in `scripts/` directory, uv is installed  
**Won't run:** Check antivirus, architecture compatibility (64-bit)  
**Clean:** `rm -rf ../build ../dist` then rebuild
