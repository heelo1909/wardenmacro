#!/bin/bash
# Runs Warden straight from the source code (always the latest fixes, no
# rebuild needed). Double-click this file in Finder.
#
# First time only: this also creates a local .venv and installs Warden's
# dependencies, so there's nothing to set up by hand before the first run.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python3" ]; then
    echo "First run - setting up Warden (this only happens once)..."
    python3 -m venv .venv || { echo "Couldn't create a virtual environment - is Python 3.12+ installed?"; read -r -p "Press Enter to close."; exit 1; }
    ".venv/bin/pip" install --upgrade pip
    ".venv/bin/pip" install -r requirements.txt
fi

".venv/bin/python3" -m warden
status=$?

if [ $status -ne 0 ]; then
    echo
    echo "Warden exited with an error (code $status)."
    echo "If this is the first run, check System Settings -> Privacy & Security for"
    echo "'Screen Recording' and 'Accessibility' - Warden needs both to see and control Roblox."
    read -r -p "Press Enter to close."
fi
