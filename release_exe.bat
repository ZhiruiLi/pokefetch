@echo off
setlocal

cd /d "%~dp0"
set "DIST_DIR=%~dp0dist"
set "ZIP_PATH=%DIST_DIR%\pokefetch.zip"

echo [1/5] Cleaning old build artifacts...
if exist "build" (
    rmdir /s /q "build"
)
if exist "dist" (
    rmdir /s /q "dist"
)
if exist "pokefetch.spec" (
    del /f /q "pokefetch.spec"
)

echo [2/5] Rebuilding pokefetch.exe...
call "%~dp0build_exe.bat"
if errorlevel 1 (
    echo Release build failed.
    exit /b 1
)

echo [3/5] Verifying output...
if not exist "%DIST_DIR%\pokefetch.exe" (
    echo Missing output: %DIST_DIR%\pokefetch.exe
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
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%DIST_DIR%\pokefetch.exe','%DIST_DIR%\config\name_mapping.txt','%DIST_DIR%\config\ignore_skills.txt' -DestinationPath '%ZIP_PATH%' -Force"
if errorlevel 1 (
    echo Failed to create archive: %ZIP_PATH%
    exit /b 1
)
if not exist "%ZIP_PATH%" (
    echo Missing archive: %ZIP_PATH%
    exit /b 1
)

echo [5/5] Release build completed.
echo Output: %DIST_DIR%\pokefetch.exe
echo Archive: %ZIP_PATH%

exit /b 0
