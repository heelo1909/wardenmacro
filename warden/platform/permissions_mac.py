"""macOS privacy permissions Warden needs, checked the normal, documented way.

Warden never works around these: it asks macOS whether each one is granted,
explains why it's needed, and opens the right System Settings pane so the
user can decide. Nothing here changes a permission by itself.

- Accessibility     (send clicks and key presses)  AXIsProcessTrusted
- Screen Recording  (see the game)                 CGPreflightScreenCaptureAccess / CGRequestScreenCaptureAccess
- Input Monitoring  (global hotkeys)               IOHIDCheckAccess / IOHIDRequestAccess

The OS calls go through ``ctypes`` against the system frameworks, so no extra
pyobjc packages are needed. ``SystemApi`` is the swappable seam for tests.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_APP_SERVICES = "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
_CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
_IOKIT = "/System/Library/Frameworks/IOKit.framework/IOKit"
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

_IOHID_REQUEST_LISTEN_EVENT = 1  # kIOHIDRequestTypeListenEvent
_IOHID_ACCESS_GRANTED = 0        # kIOHIDAccessTypeGranted

_SETTINGS = "x-apple.systempreferences:com.apple.preference.security?"


@dataclass(frozen=True)
class Permission:
    key: str
    title: str
    why: str
    settings_url: str
    steps: str
    needs_reopen: bool = False


PERMISSIONS: tuple[Permission, ...] = (
    Permission(
        key="accessibility",
        title="Accessibility",
        why="Lets Warden click and press keys in Roblox for you.",
        settings_url=_SETTINGS + "Privacy_Accessibility",
        steps="Open System Settings → Privacy & Security → Accessibility, turn on Warden "
              "(use the + button to add it from Applications if it isn't listed).",
    ),
    Permission(
        key="screen_recording",
        title="Screen Recording",
        why="Lets Warden see the Roblox window so it knows what's on screen.",
        settings_url=_SETTINGS + "Privacy_ScreenCapture",
        steps="Open System Settings → Privacy & Security → Screen & System Audio Recording "
              "(called Screen Recording on older macOS), turn on Warden, then reopen Warden.",
        needs_reopen=True,
    ),
    Permission(
        key="input_monitoring",
        title="Input Monitoring",
        why="Lets your Start/Pause/Stop hotkeys work while Roblox is in front.",
        settings_url=_SETTINGS + "Privacy_ListenEvent",
        steps="Open System Settings → Privacy & Security → Input Monitoring, turn on Warden, "
              "then reopen Warden if the hotkeys still don't respond.",
    ),
)


class SystemApi:
    """Thin ctypes wrapper over the three framework calls. macOS only."""

    def __init__(self):
        if sys.platform != "darwin":
            raise OSError("macOS permission checks require macOS")
        self._ax = ctypes.cdll.LoadLibrary(_APP_SERVICES)
        self._ax.AXIsProcessTrusted.restype = ctypes.c_bool
        self._cg = ctypes.cdll.LoadLibrary(_CORE_GRAPHICS)
        self._cg.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        self._cg.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        self._iokit = ctypes.cdll.LoadLibrary(_IOKIT)
        self._iokit.IOHIDCheckAccess.restype = ctypes.c_uint32
        self._iokit.IOHIDCheckAccess.argtypes = [ctypes.c_uint32]
        self._iokit.IOHIDRequestAccess.restype = ctypes.c_bool
        self._iokit.IOHIDRequestAccess.argtypes = [ctypes.c_uint32]

    def accessibility(self) -> bool:
        return bool(self._ax.AXIsProcessTrusted())

    def request_accessibility(self) -> bool:
        """AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: true}): macOS
        adds Warden to the Accessibility list and shows its own prompt."""
        cf = ctypes.cdll.LoadLibrary(_CORE_FOUNDATION)
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                          ctypes.POINTER(ctypes.c_void_p), ctypes.c_long,
                                          ctypes.c_void_p, ctypes.c_void_p]
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        self._ax.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        self._ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
        key = ctypes.c_void_p.in_dll(self._ax, "kAXTrustedCheckOptionPrompt")
        true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")
        keys = (ctypes.c_void_p * 1)(key.value)
        values = (ctypes.c_void_p * 1)(true.value)
        key_cbs = ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        value_cbs = ctypes.c_byte.in_dll(cf, "kCFTypeDictionaryValueCallBacks")
        options = cf.CFDictionaryCreate(None, keys, values, 1,
                                        ctypes.addressof(key_cbs), ctypes.addressof(value_cbs))
        try:
            return bool(self._ax.AXIsProcessTrustedWithOptions(options))
        finally:
            if options:
                cf.CFRelease(options)

    def screen_recording(self) -> bool:
        return bool(self._cg.CGPreflightScreenCaptureAccess())

    def request_screen_recording(self) -> bool:
        return bool(self._cg.CGRequestScreenCaptureAccess())

    def input_monitoring(self) -> bool:
        return int(self._iokit.IOHIDCheckAccess(_IOHID_REQUEST_LISTEN_EVENT)) == _IOHID_ACCESS_GRANTED

    def request_input_monitoring(self) -> bool:
        return bool(self._iokit.IOHIDRequestAccess(_IOHID_REQUEST_LISTEN_EVENT))


class PermissionChecker:
    """What the Mac setup screen talks to. ``api``/``opener`` are injectable for tests."""

    def __init__(self, api=None, opener=None):
        self._api = api
        self._opener = opener or _open_url

    @property
    def api(self):
        if self._api is None:
            self._api = SystemApi()
        return self._api

    def status(self) -> dict[str, bool]:
        out = {}
        for perm in PERMISSIONS:
            try:
                out[perm.key] = bool(getattr(self.api, perm.key)())
            except Exception:
                log.debug("permission check %s failed", perm.key, exc_info=True)
                out[perm.key] = False
        return out

    def all_granted(self) -> bool:
        return all(self.status().values())

    def request(self, key: str) -> None:
        """Ask macOS to show its own prompt where one exists (it only does so once per app)."""
        fn = getattr(self.api, f"request_{key}", None)
        if fn is None:
            return
        try:
            fn()
        except Exception:
            log.debug("permission request %s failed", key, exc_info=True)

    def open_settings(self, key: str) -> bool:
        """Open the System Settings pane for ``key``. False if the deep link failed,
        so the caller shows the written steps instead."""
        perm = next((p for p in PERMISSIONS if p.key == key), None)
        if perm is None:
            return False
        try:
            return bool(self._opener(perm.settings_url))
        except Exception:
            log.debug("opening settings for %s failed", key, exc_info=True)
            return False


def _open_url(url: str) -> bool:
    result = subprocess.run(["open", url], check=False, capture_output=True, timeout=10)
    return result.returncode == 0


def relaunch_command(executable: str | None = None, frozen: bool | None = None) -> list[str]:
    """The command that starts a fresh copy of Warden (used by "Reopen Warden").

    Packaged: ``open -n /Applications/Warden.app`` (the .app containing the
    running binary). From source: the same Python running ``-m warden``.
    """
    executable = executable or sys.executable
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if frozen:
        exe = Path(executable)
        for parent in exe.parents:
            if parent.suffix == ".app":
                return ["open", "-n", str(parent)]
        return [str(exe)]
    return [executable, "-m", "warden"]
