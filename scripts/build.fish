#!/usr/bin/env fish

echo "Building tina Executables..."
echo

# Get the script directory and project root
set script_dir (dirname (status --current-filename))
set project_root (realpath "$script_dir/..")

echo "Project root: $project_root"
echo

echo "Installing/updating PyInstaller..."
cd $project_root
uv add --group dev pyinstaller
if test $status -ne 0
    echo "ERROR: Failed to install PyInstaller"
    exit 1
end
echo

echo "Cleaning previous builds..."
cd $project_root
rm -rf build dist
echo

echo "Building main TUI executable (tina)..."
cd $project_root
uv run pyinstaller --clean scripts/tina.spec
if test $status -ne 0
    echo "ERROR: Failed to build main executable"
    exit 1
end
echo

echo "Building quick measure executable (tina-quick)..."
cd $project_root
uv run pyinstaller --clean scripts/tina-quick.spec
if test $status -ne 0
    echo "ERROR: Failed to build quick measure executable"
    exit 1
end
echo

echo "Build completed successfully!"
echo

echo "Executables created:"
echo "  dist/tina        - Main TUI application"
echo "  dist/tina-quick  - Quick measure (double-click to measure)"
echo

echo "You can distribute these executables to users."
echo "Note: Linux/macOS users can also use 'uv tool install' for easier installation."
echo
