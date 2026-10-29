"""M3: Mac permissions logic, first-run Mac defaults, and Windows seeding untouched."""

import os
import sys
import tempfile
from pathlib import Path

from _util import ROOT, check, run


class _Api:
    def accessibility(self): return True
    def screen_recording(self): return False
    def input_monitoring(self): return True


def main():
    from warden.platform.permissions_mac import PermissionChecker, relaunch_command
    from warden.platform.macos import MAC_HOTKEYS, mac_first_run_defaults

    opened = []
    pc = PermissionChecker(api=_Api(), opener=lambda u: opened.append(u) or True)
    check("status of all three", pc.status() == {"accessibility": True, "screen_recording": False,
                                                 "input_monitoring": True})
    check("deep link opens", pc.open_settings("screen_recording") and opened[0].endswith("Privacy_ScreenCapture"))
    check("relaunch uses the .app", relaunch_command("/Applications/Warden.app/Contents/MacOS/Warden", True)[:2] == ["open", "-n"])
    out = mac_first_run_defaults({"hotkeys": {"start": "F6", "pause": "F7", "stop": "F8", "screenshot": "F9"}})
    check("Mac hotkeys", out["hotkeys"] == MAC_HOTKEYS)
    check("OCR off on Mac", out["estimate"]["ocr_verify"] is False)

    from warden.config import loader

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["WARDEN_HOME"] = tmp
        real = sys.platform
        try:
            loader.sys.platform = "win32"
            loaded = loader.load_all()
        finally:
            loader.sys.platform = real
        check("Windows first run is a plain copy",
              Path(loaded.app_path).read_bytes() == (ROOT / "config" / "default.yaml").read_bytes())


run(main)
