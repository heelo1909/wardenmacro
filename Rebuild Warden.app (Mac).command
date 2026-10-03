#!/bin/bash
# Rebuilds dist/Warden.app from the current source code. Run this after any
# code change - the .app does not update by itself. Must be run ON a Mac;
# PyInstaller builds a native app for whatever OS it's running on.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/pyinstaller" ]; then
    echo "First run - setting up Warden (this only happens once)..."
    python3 -m venv .venv || { echo "Couldn't create a virtual environment - is Python 3.12+ installed?"; read -r -p "Press Enter to close."; exit 1; }
    ".venv/bin/pip" install --upgrade pip
    ".venv/bin/pip" install -r requirements.txt pyinstaller
fi

".venv/bin/pyinstaller" warden.spec --clean --noconfirm

echo
echo "Done. The new app is dist/Warden.app"
read -r -p "Press Enter to close."
