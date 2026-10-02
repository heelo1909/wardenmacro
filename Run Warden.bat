@echo off
rem Runs Warden straight from the source code (always the latest fixes,
rem no rebuild needed). Double-click this file.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m warden
if errorlevel 1 pause
