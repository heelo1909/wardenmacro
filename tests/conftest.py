import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# GUI tests must never pop real windows.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def warden_home(tmp_path, monkeypatch):
    """Point the data folder at a temp dir so tests never touch %LOCALAPPDATA%\\Warden."""
    home = tmp_path / "warden_home"
    monkeypatch.setenv("WARDEN_HOME", str(home))
    return home


@pytest.fixture
def bundled_config():
    return ROOT / "config"
