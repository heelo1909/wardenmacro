# BUG-001: Mac CI crashes on exit after the Mac port tests pass

- **Reported:** 2026-10-29
- **OS / build:** Mac (arm64 and Intel), GitHub Actions `macos-15` runners, tag `v0.1.0` (run 40916293036)
- **Stage:** B-001
- **Status:** fixed (offline)

## What the user said
> push it so theres a dmg build
> is it done

## Evidence
- Log lines: the "Mac port tests (must pass)" step printed every dot to `[100%]`, then
  `QObject: shared QObject was deleted directly. The program is malformed and may crash.`, then
  `Bus error: 10` (arm64, exit 138) / `Segmentation fault: 11` (x86_64, exit 139). Every later step was
  skipped, so no DMG was built and "Attach to GitHub Release" failed on `test -f out/Warden-mac-arm64.dmg`.
- What the evidence shows: no test failed. The process died after the last test, while Python tore down Qt.
  `tests/test_mac_port.py` creates a module-scoped `QApplication` and `MacSetupPage`/`MainWindow` widgets
  that are closed but never deleted, so the interpreter decided the destruction order. Not reproducible on
  macOS 27 locally (exits 0); it happens on GitHub's macOS 15 images.

## Root cause
Qt objects were left to Python's interpreter shutdown, which can destroy the `QApplication` before the
widgets that depend on it. On macOS 15 that crashes the process, which turned a passing test step red.

## Fix
- `tests/qt_teardown.py: shutdown_qt_app()` closes and deletes every top-level widget, flushes deferred
  deletes, then calls `QApplication.shutdown()` (PySide6's supported fix for destruction-order crashes).
  `tests/conftest.py` calls it from `pytest_sessionfinish`. Test-only change: the app is untouched.
- Regression test: `tests/test_qt_teardown.py`
- Smoke check: `smoke_checks/b_001_qt_teardown.py`
- Commit: B-001

## Live confirmation needed?
yes. It can only be confirmed on GitHub's macOS 15 runners: a green "Mac release" run
(build-only run 40917054897 on branch `b-001-qt-teardown`, then the release tag).
