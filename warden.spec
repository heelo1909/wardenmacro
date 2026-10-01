# PyInstaller spec - one-folder build (HANDOFF §9, Phase 9).
#
#   .venv\Scripts\pyinstaller.exe warden.spec --clean
#
# Produces dist\Warden\Warden.exe plus its folder of dependencies. config\
# ships as the *defaults* that get copied into %LOCALAPPDATA%\Warden on
# first run (warden/config/loader.py's seed_user_config) - the installed
# copy is never written to.
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
    "winotify",
    "pydirectinput",
    "pytesseract",
    "win32gui", "win32con", "win32process",  # pywin32, used indirectly on Windows
]

a = Analysis(
    ["scripts/run_warden.py"],
    pathex=["."],
    binaries=[],
    datas=[("config", "config")],
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
