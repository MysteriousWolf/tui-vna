@echo off
echo Building tina Executables...
echo.

echo Installing/updating PyInstaller...
pushd ..
uv add --group dev pyinstaller
popd
echo.

echo Cleaning previous builds...
pushd ..
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
popd
echo.

echo Building main GUI executable (tina.exe)...
pushd ..
uv run pyinstaller --clean scripts\tina.spec
if errorlevel 1 (
    echo ERROR: Failed to build main executable
    popd
    pause
    exit /b 1
)
popd
echo.

echo Building quick measure executable (tina-quick.exe)...
pushd ..
uv run pyinstaller --clean scripts\tina-quick.spec
if errorlevel 1 (
    echo ERROR: Failed to build quick measure executable
    popd
    pause
    exit /b 1
)
popd
echo.

echo Build completed successfully!
echo.
echo Executables created:
echo   dist\tina.exe        - Main GUI application
echo   dist\tina-quick.exe  - Quick measure (double-click to measure)
echo.
echo You can distribute these .exe files to Windows users.
echo They are standalone and don't require Python installation.
echo.
pause
