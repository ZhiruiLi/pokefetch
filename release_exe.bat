@echo off
setlocal

cd /d "%~dp0"

echo [1/4] Cleaning old build artifacts...
if exist "build" (
    rmdir /s /q "build"
)
if exist "dist" (
    rmdir /s /q "dist"
)
if exist "pokefetch.spec" (
    del /f /q "pokefetch.spec"
)

echo [2/4] Rebuilding pokefetch.exe...
call "%~dp0build_exe.bat"
if errorlevel 1 (
    echo Release build failed.
    exit /b 1
)

echo [3/4] Verifying output...
if not exist "dist\pokefetch.exe" (
    echo Missing output: dist\pokefetch.exe
    exit /b 1
)

echo [4/4] Release build completed.
echo Output: dist\pokefetch.exe

exit /b 0
