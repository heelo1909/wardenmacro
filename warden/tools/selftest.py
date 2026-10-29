"""``warden --selftest``: prove a build is wired up, without Roblox or a screen.

Imports every module Warden needs at runtime, validates the bundled config,
checks the shipped templates are present, and prints platform info. On macOS
it also loads the Quartz/AppKit bindings and calls the three permission
checks (read-only - nothing is requested), which proves the framework symbols
resolve inside the packaged app. Exit code 0 = all good, 1 = something failed.

Used by the GitHub Actions Mac workflow against the built ``Warden.app``, and
safe to run anywhere: it never opens a window, sends input, or touches the
user's real data folder.
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

CORE_MODULES = (
    "numpy", "cv2", "yaml", "pydantic", "mss", "psutil",
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "warden.config", "warden.core.state_machine", "warden.core.tick",
    "warden.platform.window", "warden.platform.input", "warden.platform.power",
    "warden.platform.process", "warden.platform.hotkeys", "warden.platform.retina",
    "warden.vision.capture", "warden.vision.templates", "warden.vision.detectors",
    "warden.flows.loadout", "warden.flows.recovery",
    "warden.gui.main_window",
)
MAC_MODULES = (
    "Quartz", "AppKit",
    "warden.platform.window_mac", "warden.platform.input_mac",
    "warden.platform.permissions_mac", "warden.platform.macos", "warden.gui.pages.mac_setup",
)


def _check(name: str, fn: Callable[[], str | None], out: list[str]) -> bool:
    try:
        detail = fn()
    except Exception as exc:  # report, don't raise - the point is a full list
        out.append(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        return False
    out.append(f"ok    {name}" + (f" ({detail})" if detail else ""))
    return True


def run(platform_name: str | None = None, emit: Callable[[str], None] = print) -> int:
    platform_name = platform_name or sys.platform
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # never needs a display
    from warden import APP_NAME, __version__, paths

    lines: list[str] = [
        f"{APP_NAME} {__version__} selftest",
        f"platform  {platform_name} / {platform.machine()} / macOS {platform.mac_ver()[0] or '-'}",
        f"python    {sys.version.split()[0]} ({'frozen app' if getattr(sys, 'frozen', False) else 'source'})",
        f"bundle    {paths.repo_root()}",
    ]
    ok = True
    modules = CORE_MODULES + (MAC_MODULES if platform_name == "darwin" else ())
    for mod in modules:
        ok &= _check(f"import {mod}", lambda m=mod: (importlib.import_module(m), None)[1], lines)

    def bundled_config() -> str:
        from warden.config.loader import load_app_config, load_preset

        cfg_dir = paths.bundled_config_dir()
        load_app_config(cfg_dir / "default.yaml")
        presets = sorted((cfg_dir / "presets").glob("*.yaml"))
        for p in presets:
            load_preset(p)
        return f"default.yaml + {len(presets)} presets"

    ok &= _check("bundled config validates", bundled_config, lines)

    def templates() -> str:
        found = sorted(p.name for p in (paths.repo_root() / "templates").glob("*.png"))
        if not found:
            raise FileNotFoundError("no templates/*.png bundled")
        return f"{len(found)} templates"

    ok &= _check("shipped templates present", templates, lines)

    def first_run_seed() -> str:
        # Seeds into a throwaway folder, never the user's real data home.
        from warden.config import load_all

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("WARDEN_HOME")
            os.environ["WARDEN_HOME"] = tmp
            try:
                loaded = load_all()
                return f"preset '{loaded.preset_id}', hotkeys start={loaded.app.hotkeys.start}"
            finally:
                if old is None:
                    os.environ.pop("WARDEN_HOME", None)
                else:
                    os.environ["WARDEN_HOME"] = old

    ok &= _check("first-run config seed", first_run_seed, lines)

    if platform_name == "darwin":
        def permissions() -> str:
            from warden.platform.permissions_mac import PermissionChecker

            status = PermissionChecker().status()  # read-only checks
            return ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in status.items())

        ok &= _check("permission checks callable", permissions, lines)

        def quartz_input() -> str:
            from warden.platform.input_mac import QuartzMethod

            QuartzMethod()  # constructs only; posts nothing
            return "constructed"

        ok &= _check("Quartz input backend", quartz_input, lines)

    lines.append("RESULT    " + ("PASS" if ok else "FAIL"))
    text = "\n".join(lines)
    emit(text)
    _also_write_file(text)
    return 0 if ok else 1


def _also_write_file(text: str) -> None:
    """Windowed builds may have no stdout; leave a copy in the temp folder."""
    try:
        Path(tempfile.gettempdir(), "warden-selftest.txt").write_text(text + "\n", encoding="utf-8")
    except Exception:
        pass
