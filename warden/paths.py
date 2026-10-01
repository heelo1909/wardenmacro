"""Filesystem locations.

User data lives under %LOCALAPPDATA%\\Warden. Set WARDEN_HOME to override
(tests do this so they never touch the real data folder).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from warden import APP_NAME


def repo_root() -> Path:
    """Folder holding the bundled config/ and fixtures/ (works frozen too)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def bundled_config_dir() -> Path:
    return repo_root() / "config"


def data_home() -> Path:
    override = os.environ.get("WARDEN_HOME")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def data_dir(name: str) -> Path:
    """A named subfolder of the data home (logs, sessions, diagnostics, ...), created on demand."""
    path = data_home() / name
    path.mkdir(parents=True, exist_ok=True)
    return path
