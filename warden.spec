# PyInstaller spec - one-folder build (HANDOFF §9, Phase 9).
#
#   Windows:  .venv\Scripts\pyinstaller.exe warden.spec --clean
#   macOS:    .venv/bin/pyinstaller warden.spec --clean   (run ON a Mac - PyInstaller
#             builds a native app for whatever OS it's running on, it can't
#             cross-compile a .app from Windows/Linux or an .exe from a Mac)
#
# Produces dist/Warden/Warden.exe on Windows, or dist/Warden.app on macOS,
# each with its own folder of bundled dependencies. config/ ships as the
# *defaults* copied into the user data folder on first run
# (warden/config/loader.py's seed_user_config) - the installed copy is never
# written to.
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Optional integrations (Phase 7) are imported lazily inside functions, so
# PyInstaller's static analysis won't find them on its own - list them
# explicitly. Each one is still a soft dependency at runtime (every
# integration degrades gracefully if its package isn't installed/bundled).
hidden_imports = [
    *collect_submodules("discord"),
    *collect_submodules("fastapi"),
    *collect_submodules("uvicorn"),
    "pytesseract",
]
if sys.platform == "win32":
    hidden_imports += [
        "winotify",
        "pydirectinput",
        "win32gui", "win32con", "win32process",  # pywin32, used indirectly on Windows
    ]
elif sys.platform == "darwin":
    hidden_imports += [*collect_submodules("Quartz"), *collect_submodules("AppKit")]

a = Analysis(
    ["scripts/run_warden.py"],
    pathex=["."],
    binaries=[],
    datas=[("config", "config"), ("templates", "templates")],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Warden",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app - no console window
    disable_windowed_traceback=False,
    icon=None,  # set once a real Lucide/MIT icon is chosen and converted to .ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Warden",
)

if sys.platform == "darwin":
    # Wraps the same COLLECT output as a double-clickable Warden.app instead
    # of a bare folder - macOS users expect an .app, not an exe-style folder.
    # PyInstaller ad-hoc signs the bundle (required on Apple Silicon); see
    # scripts/mac/build_dmg.sh and .github/workflows/mac-release.yml.
    import os
    import re

    _init = open(os.path.join(SPECPATH, "warden", "__init__.py"), encoding="utf-8").read()
    _warden_version = re.search(r'__version__\s*=\s*"([^"]+)"', _init).group(1)

    app = BUNDLE(
        coll,
        name="Warden.app",
        icon="assets/warden.icns",  # original placeholder icon (assets/warden.png)
        bundle_identifier="com.heelo1909.warden",
        version=_warden_version,
        info_plist={
            "CFBundleName": "Warden",
            "CFBundleDisplayName": "Warden",
            "CFBundleShortVersionString": _warden_version,
            "CFBundleVersion": _warden_version,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "13.0",  # current Qt 6 needs macOS 13 Ventura+
            "LSApplicationCategoryType": "public.app-category.utilities",
            # Shown by macOS the first time Warden uses osascript for a
            # notification or the optional end-of-session sleep/shut down.
            "NSAppleEventsUsageDescription":
                "Warden uses this to show notifications and, only if you turn it on, "
                "to put your Mac to sleep or shut it down when a session ends.",
        },
    )
