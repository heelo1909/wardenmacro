# HANDOFF: Warden for Mac (port and DMG release)

> **Status (2026-10-29):** Phases 0–4 are built and their code is in this repo.
> Next up is the **Phase 4 user test** (push + test tag), then **Phase 5** (real Mac).
> `PROGRESS.md` → "Mac port" has the Phase 0 inventory, decisions and known issues.

## 0. Read first (Claude Code)

- Build one phase at a time, keep `PROGRESS.md` updated, and **STOP after every phase** with a Phase Report. Wait for "go", "fix: ...", or "redo".
- The user can't code and doesn't have a personal Mac with Terminal. **All Mac building happens on GitHub's macOS runners** (GitHub Actions). Real-device testing happens on a personally owned Mac (a family member's or friend's), never a school or work Mac.
- **Don't break Windows.** Mac code stays behind the existing platform seams (`make_window_backend()`, the `InputMethod` chain, `Capturer`, `SleepGuard`, `power_action`) or behind `sys.platform == "darwin"`. Windows behavior stays identical.
- **Testing baseline:** in a Linux sandbox the suite is 515 tests with **40 known environment-only failures** (Win32 ctypes, pynput without an X display). "No new failures" is the bar there. On Windows, the full suite must pass as before. Never run a live `TickLoop` against a real Roblox client in tests (see PROGRESS.md Decisions #29).

## 1. Goal

Warden runs on personally owned Macs (Apple Silicon first, Intel while GitHub still offers `macos-15-intel`, scheduled to retire in 2027) and ships as a **.dmg** on GitHub Releases, so users never need Terminal or file-permission changes.

## 2. Ground rules

- **Personal Macs only.** School and work Macs are managed devices and are not supported. Don't add anything that works around device management, Gatekeeper, or macOS privacy permissions. The app asks for permissions the normal way and explains why. The README says managed Macs aren't supported.
- Same safety notes as the Windows version (the ban-risk caveat, no credentials stored or typed).
- No secrets in the repo or in CI logs. The workflow uses only the built-in `GITHUB_TOKEN`.

## 3. Where each Windows piece stands on Mac

| Area | Windows | Mac (file) | State |
|---|---|---|---|
| Clicks and keys | SendInput, pydirectinput | Quartz CGEvent `platform/input_mac.py`, pynput fallback; `MAC_KEYCODES` | Built, mocked tests |
| Finding Roblox | Win32 window APIs | `platform/window_mac.py` (Quartz window list, process `robloxplayer`) | Built; **process name unverified** |
| Title bar | GetClientRect (content only) | `retina.content_rect`, `mac.title_bar_pt` = 28, none in fullscreen | Built; verify the 28 pt |
| Focusing Roblox | SetForegroundWindow | `NSRunningApplication.activateWithOptions_` | Built |
| Screen capture | PrintWindow | `CGWindowListCreateImage` clipped to content rect | Built; API obsolete in the macOS 15 SDK, see risks |
| Retina | DPI awareness | `platform/retina.py`; frames are always in points | Built, tested at scale 1 and 2 |
| Main loop | `TickLoop` | Was hardcoded to `Win32Windows()`; now `make_window_backend()` | **Fixed** |
| Sleep prevention | SetThreadExecutionState | `caffeinate` | Built (earlier round) |
| Launch / kill Roblox | os.startfile, terminate | `open roblox://...`, psutil | Built (earlier round) |
| Hotkeys | pynput GlobalHotKeys, F6–F9 | Key-code matcher, Ctrl+Shift+S/P/X/K defaults, rebindable | Built; verify on a Mac |
| OCR | Tesseract | Off by default (`mac.ocr: false`), features degrade | Built |
| Permissions | — | `platform/permissions_mac.py` + Mac setup page | Built |
| Packaging | PyInstaller folder | `.app` → `.dmg` on GitHub Actions | Built, **never run yet** |

## 4. Mac setup screen (built)

`gui/pages/mac_setup.py`, shown at launch while anything is missing: Accessibility (`AXIsProcessTrusted`), Screen Recording (`CGPreflightScreenCaptureAccess` / `CGRequestScreenCaptureAccess`, then "Reopen Warden"), Input Monitoring (`IOHIDCheckAccess`). Each row: one-sentence reason, green tick, "Open System Settings" deep link, written steps if the link fails. macOS ties permissions to the app's signature, so an update with a new ad-hoc signature may ask again (in the README).

## 5. Packaging and release (built)

- `warden.spec` → `Warden.app` (`com.heelo1909.warden`, `assets/warden.icns`, minimum macOS 13). Ad-hoc signed; not notarized.
- `scripts/mac/build_dmg.sh` → `Warden-mac-<arch>.dmg` with an Applications link (`hdiutil create -volname "Warden" ... -format UDZO`).
- `.github/workflows/mac-release.yml` runs on `v*` tags (and "Run workflow"): `macos-15` arm64 and `macos-15-intel` x86_64 (best-effort), Python 3.12, Mac tests (blocking), full suite (report only), `--selftest` from source, from the built app, and from inside the mounted DMG, then attaches the DMGs to the release. Tags with a dash become pre-releases.
- `warden --selftest` checks imports, bundled config, templates, the first-run seed and (on Mac) the Quartz/AppKit bindings and permission calls. It never opens a window or sends input.

## 6. README Mac section (written)

Install → Mac: which DMG to pick (Apple menu → About This Mac → Chip), drag to Applications, "Open Anyway" in Privacy & Security, the Mac setup screen, managed Macs unsupported, Mac hotkeys, OCR off, re-granting after updates. Confirm the wording against what a real Mac shows in Phase 5.

## 7. Phases

### Phase 0: Inspect and plan — DONE
Inventory with file and line is in PROGRESS.md. The repo already had the platform seams the original plan proposed, so no new interface layer was added.

### Phase 1: Platform interface, no behavior change — DONE
Only `TickLoop` bypassed a seam; it now uses `make_window_backend()`. Same 40 environment-only failures as before; with fakes injected, the 58 TickLoop/GUI tests that need Windows pass in the sandbox.

### Phase 2: Mac backend — DONE (mocked)
Quartz input + key map, Retina helpers, title-bar trim, display scale, capture clipped to content. Unit tests: scale 1 and 2, key map, window detection from a fake window list.

### Phase 3: Mac setup screen and defaults — DONE (mocked)
Permissions page, Mac hotkey defaults, OCR off. No screenshot possible without a Mac; offscreen Qt tests cover it.

### Phase 4: Packaging and CI — BUILT, USER TEST PENDING
1. Commit and push the repo to `github.com/heelo1909/wardenmacro` (`main`).
2. Push a test tag: `v0.0.1-mactest`. (No Terminal? On GitHub: Releases → Draft a new release → "Choose a tag" → type `v0.0.1-mactest` → "Create new tag on publish" → tick "Set as a pre-release" → Publish. Publishing creates the tag, which starts the workflow; it then adds the DMGs to that release.)
3. **User test:** Actions tab → "Mac release" run is green (the Intel leg may show as allowed-to-fail). Releases → `v0.0.1-mactest` has `Warden-mac-arm64.dmg` (and `Warden-mac-x86_64.dmg` if Intel passed).
4. If anything fails, paste the failing step's log into Claude Code with "fix: ...".
- DoD: [ ] workflow builds the DMG on tag push [ ] selftest passes on the runner [ ] DMG attached to the release

### Phase 5: Real-Mac test and release — TODO
On a personally owned Mac, signed in to an **alt** Roblox account. Record pass/fail for each:
1. Download the right DMG, open it, drag Warden to Applications, open it, use "Open Anyway". Warden opens.
2. Mac setup page appears; allow all three permissions; "Reopen Warden"; all three show a green tick.
3. Diagnostics page: Roblox window found while RIVALS is open (confirms the process name).
4. Calibration → capture a live frame, windowed and fullscreen: the image shows the game with **no title bar** and colors look right (red/blue not swapped).
5. Start with Roblox in the lobby: Play and the FFA tile get clicked where they should (no offset strip).
6. In a match: loadout gets picked; respawn key works; camera look moves.
7. Hotkeys Ctrl+Shift+S / P / X / K work while Roblox is in front.
8. Reconnect: quit Roblox mid-match; Warden relaunches it and gets back into FFA.
9. Emergency stop: the stop hotkey halts all input. (The top-left-corner stop is **not wired on any OS** today; decide whether to wire it before claiming it works.)
10. Mac stays awake during a session (caffeinate); a notification shows on stop.
Fix what fails (each fix: Windows tests still pass), then tag a normal release (`v0.2.0`).
- DoD: [ ] tested on a personally owned Mac [ ] README Mac section confirmed [ ] normal release published

## 8. Risks to watch

- `CGWindowListCreateImage` is obsolete in the macOS 15 SDK. It still works at runtime (and `mss` uses it), but some macOS 26 reports show desktop-only captures. If step 4 shows blank or desktop frames, move capture to ScreenCaptureKit.
- New ad-hoc signature per build → permissions may need re-granting after each update. Notarization (paid Apple Developer account) would fix the first-launch warning, not this.
- `macos-15-intel` is GitHub's last Intel image (retires 2027). After that, Intel Macs need a universal2 build or are dropped.

## 9. Kickoff prompt (paste into Claude Code in the repo folder)

> Read warden-mac-handoff.md and the "Mac port" section of PROGRESS.md in full. Phases 0–4 are built; Phase 4's user test is next. Help me push the code and the `v0.0.1-mactest` tag (I can't use Terminal on a Mac; I'm on Windows), then wait while I check the Actions run and the Releases page. If the run fails, fix only what the log shows, then STOP with a Phase Report (Built, Tested by me, Could not test, Known issues, Your test, I need from you). Do not start Phase 5 until I reply "go". Never change how the Windows version behaves. Never add anything that works around device management or macOS permissions.
