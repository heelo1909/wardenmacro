"""TickLoop must not crash constructing if the LAN dashboard is enabled but
fastapi/uvicorn aren't installed - the integration just stays off.
"""

import builtins
import shutil

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.tick import TickLoop


def test_lan_dashboard_missing_fastapi_degrades_gracefully(bundled_config, tmp_path, monkeypatch):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    loaded.app.integrations.lan_dashboard.enabled = True

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "fastapi":
            raise ImportError("no fastapi")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    loop = TickLoop(loaded.app, loaded.preset, EventBus())
    assert loop.lan_dashboard is None
