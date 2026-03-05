@echo off
setlocal

cd /d "%~dp0"

set "SPEC_FILE=%~1"
if "%SPEC_FILE%"=="" set "SPEC_FILE=pokefetch.spec"

set "EXE_NAME=%~2"
if "%EXE_NAME%"=="" set "EXE_NAME=pokefetch"

set "DIST_DIR=%~dp0dist"
set "EXE_PATH=%DIST_DIR%\%EXE_NAME%.exe"
set "ZIP_PATH=%DIST_DIR%\%EXE_NAME%.zip"

echo Using spec: %SPEC_FILE%
echo Target exe: %EXE_NAME%.exe

echo [1/5] Cleaning old build artifacts...
if exist "build" (
    rmdir /s /q "build"
)
if exist "dist" (
    rmdir /s /q "dist"
)

if not exist "%SPEC_FILE%" (
    echo Missing spec file: %SPEC_FILE%
    echo Usage: release_exe.bat [spec_file] [exe_name]
    exit /b 1
)

echo [2/5] Checking PyInstaller...
uv run pyinstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller not found in environment. Installing as dev dependency...
    uv add --dev pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        exit /b 1
    )
)

echo Building %EXE_NAME%.exe from spec...
uv run pyinstaller --noconfirm --clean "%SPEC_FILE%"
if errorlevel 1 (
    echo Release build failed.
    exit /b 1
)

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%DIST_DIR%\config" mkdir "%DIST_DIR%\config"
if exist "config\name_mapping.txt" copy /y "config\name_mapping.txt" "%DIST_DIR%\config\name_mapping.txt" >nul
if exist "config\ignore_skills.txt" copy /y "config\ignore_skills.txt" "%DIST_DIR%\config\ignore_skills.txt" >nul

echo [3/5] Verifying output...
if not exist "%EXE_PATH%" (
    echo Missing output: %EXE_PATH%
    exit /b 1
)
if not exist "%DIST_DIR%\config\name_mapping.txt" (
    echo Missing output: %DIST_DIR%\config\name_mapping.txt
    exit /b 1
)
if not exist "%DIST_DIR%\config\ignore_skills.txt" (
    echo Missing output: %DIST_DIR%\config\ignore_skills.txt
    exit /b 1
)

echo [4/5] Creating release archive...
if exist "%ZIP_PATH%" (
    del /f /q "%ZIP_PATH%"
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%EXE_PATH%','%DIST_DIR%\config\name_mapping.txt','%DIST_DIR%\config\ignore_skills.txt' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 (
    echo Failed to create archive: %ZIP_PATH%
    exit /b 1
)
if not exist "%ZIP_PATH%" (
    echo Missing archive: %ZIP_PATH%
    exit /b 1
)

echo [5/5] Release build completed.
echo Output: %EXE_PATH%
echo Archive: %ZIP_PATH%

exit /b 0
