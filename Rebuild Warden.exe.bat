@echo off
rem Rebuilds dist\Warden\Warden.exe from the current source code.
rem Run this after any code change - the .exe does not update by itself.
cd /d "%~dp0"
".venv\Scripts\pyinstaller.exe" warden.spec --clean --noconfirm
echo.
echo Done. The new app is dist\Warden\Warden.exe
pause
