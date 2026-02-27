@echo off
setlocal

cd /d "%~dp0"

echo [1/3] Checking PyInstaller...
uv run pyinstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller not found in environment. Installing as dev dependency...
    uv add --dev pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        exit /b 1
    )
)

echo [2/3] Building pokefetch.exe...
uv run pyinstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --name pokefetch ^
  --add-data "template.html;." ^
  --add-data "wiki_site_styles.css;." ^
  --add-data "icons;icons" ^
  --add-data "name_mapping.txt;." ^
  --add-data "ignore_skills.txt;." ^
  main.py
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo [3/4] Syncing editable resource files to dist...
if not exist "dist" mkdir "dist"
if exist "name_mapping.txt" copy /y "name_mapping.txt" "dist\name_mapping.txt" >nul
if exist "ignore_skills.txt" copy /y "ignore_skills.txt" "dist\ignore_skills.txt" >nul

echo [4/4] Build completed.
echo Output: dist\pokefetch.exe

exit /b 0
