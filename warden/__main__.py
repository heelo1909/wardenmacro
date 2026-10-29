"""Entry point: ``python -m warden``.

Options:
  --check-config [PATH]   validate config (default: user config) and exit
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from warden import APP_NAME, __version__
from warden import paths
from warden.config import ConfigError, load_all
from warden.config.schema import LicenseConfig
from warden.core.events import bus
from warden.core.logs import bridge_bus_to_logging, setup_logging


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="warden", description=f"{APP_NAME} session runner")
    parser.add_argument("--check-config", nargs="?", const="", metavar="PATH",
                        help="validate config.yaml (and its active preset) then exit")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser.parse_args(argv)


def check_config(path: str) -> int:
    try:
        loaded = load_all(Path(path) if path else None)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"OK: {loaded.app_path} (preset '{loaded.preset_id}' from {loaded.preset_path})")
    return 0


def _ensure_licensed(license_config: LicenseConfig) -> bool:
    """Gumroad key gate (Licensing & Distribution Proposal, Phase 1 "Ship
    it"). A no-op returning True immediately unless a customer-facing build
    set ``license.enabled: true`` in config.yaml - a from-source dev copy
    never sees this prompt. Returns False only if the user cancels, so the
    caller can exit cleanly instead of opening the main window unlicensed.
    """
    from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

    from warden.flows import license as license_flow

    home = paths.data_home()
    state = license_flow.load_state(home)
    if license_flow.has_access(state, license_config):
        return True

    while True:
        key, ok = QInputDialog.getText(
            None,
            f"{APP_NAME} - License required",
            "Enter your license key (emailed by Gumroad at checkout):",
            QLineEdit.Normal,
        )
        if not ok:
            return False
        result = license_flow.verify_and_activate(key, license_config)
        if result.ok:
            license_flow.save_state(
                home,
                license_flow.LicenseState(
                    key=key.strip(), tier=result.tier, activated_at=time.time(), device_confirmed=True
                ),
            )
            return True
        QMessageBox.warning(None, f"{APP_NAME} - License", result.message)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.check_config is not None:
        return check_config(args.check_config)

    log_file = setup_logging()
    bridge_bus_to_logging(bus())
    logging.getLogger(__name__).info("%s %s starting; log file %s", APP_NAME, __version__, log_file)

    from PySide6.QtWidgets import QApplication, QMessageBox

    from warden.gui.main_window import MainWindow

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    # Force Qt's own cross-platform style instead of each OS's native one.
    # Native styles (windowsvista on Windows, macos on Mac) paint some
    # widget chrome - buttons especially - with the OS's own theming engine
    # and silently ignore custom QSS backgrounds/gradients on them. Fusion
    # respects the stylesheet fully, so theme.py renders identically on
    # Windows, Mac, and Linux instead of just wherever it was tested.
    app.setStyle("Fusion")

    try:
        config = load_all()
    except ConfigError as exc:
        logging.getLogger(__name__).error("config invalid: %s", exc)
        QMessageBox.critical(None, f"{APP_NAME} - config problem",
                             f"{exc}\n\nFix the file above (or delete it to restore defaults) and restart.")
        return 2

    if not _ensure_licensed(config.app.license):
        logging.getLogger(__name__).info("license check cancelled by user at startup; exiting")
        return 3

    window = MainWindow(config)
    window.show()
    bus().emit("app.ready", f"{APP_NAME} ready", level="info", preset=config.preset_id)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
