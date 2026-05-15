# Release Process

## Creating a Release

Version is tracked exclusively via git tags — no manual version bumps in source files needed.

### Option A: GitHub Actions (recommended)

1. Go to **Actions → Bump Version → Run workflow**
2. Choose bump type (`patch` / `minor` / `major`) and optionally a release title
3. The workflow verifies CI is passing on the current commit, computes the next version, and pushes the tag
4. The **Build and Release** workflow triggers automatically, builds binaries for all platforms, generates AI-assisted release notes, and publishes the GitHub Release

### Option B: Manual tag

```bash
git tag -a v0.x.y -m "Release title"
git push origin v0.x.y
```

GitHub Actions picks up the tag and handles the rest.

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** — incompatible API changes
- **MINOR** — new functionality, backwards-compatible
- **PATCH** — backwards-compatible bug fixes

In development builds (untagged commits), the version displays as `dev`.

## What Gets Built

When a tag is pushed, GitHub Actions builds six binaries:

| Platform | Full TUI | Quick (CLI only) |
|---|---|---|
| Linux x86_64 | `tina-vX.Y.Z-linux-x86_64` | `tina-quick-vX.Y.Z-linux-x86_64` |
| Windows x86_64 | `tina-vX.Y.Z-windows-x86_64.exe` | `tina-quick-vX.Y.Z-windows-x86_64.exe` |
| macOS ARM64 (Apple Silicon) | `tina-vX.Y.Z-macos-arm64` | `tina-quick-vX.Y.Z-macos-arm64` |

Monitor build progress in the Actions tab.
