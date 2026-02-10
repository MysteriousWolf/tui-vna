# Release Process

## Creating a Release

1. **Update version in both files:**
   - `pyproject.toml`: `version = "0.1.2"`
   - `src/tina/__init__.py`: `__version__ = "0.1.2"`

2. **Commit changes**

3. **Create and push tag:**

   **CLI:**

   ```bash
   git tag -a v0.1.2 -m "Release 0.1.2"
   git push --tags
   ```

   **GitHub Web:**
   - Go to Releases → Create a new release
   - Choose a tag: type `v0.1.2` and create new tag
   - Click "Publish release"

GitHub Actions will automatically generate a changelog from commits and build binaries for all platforms.

## Version Numbering

Follow [Semantic Versioning](https://semver.org/) (or embrace [0ver](https://0ver.org/) and stay in 0.x.x forever):

- **MAJOR** - incompatible API changes
- **MINOR** - new functionality, backwards-compatible
- **PATCH** - backwards-compatible bug fixes

## What Gets Built

When you push a tag like `v0.1.2`, GitHub Actions builds:

- `tina-linux-x86_64` - Main TUI for Linux
- `tina-quick-linux-x86_64` - Quick measure for Linux
- `tina-windows-x86_64.exe` - Main TUI for Windows
- `tina-quick-windows-x86_64.exe` - Quick measure for Windows
- `tina-macos-x86_64` - Main TUI for macOS
- `tina-quick-macos-x86_64` - Quick measure for macOS

Check the Actions tab to monitor build progress.
