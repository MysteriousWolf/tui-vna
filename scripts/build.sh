#!/bin/bash

echo "Building tina Executables..."
echo

echo "Installing/updating PyInstaller..."
pushd ..
uv add --group dev pyinstaller
popd
echo

echo "Cleaning previous builds..."
pushd ..
rm -rf build dist
popd
echo

echo "Building main TUI executable (tina)..."
pushd ..
uv run pyinstaller --clean scripts/tina.spec
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build main executable"
    popd
    exit 1
fi
popd
echo

echo "Building quick measure executable (tina-quick)..."
pushd ..
uv run pyinstaller --clean scripts/tina-quick.spec
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build quick measure executable"
    popd
    exit 1
fi
popd
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
