"""Entry point: ``python -m warden``.

Options:
  --check-config [PATH]   validate config (default: user config) and exit
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from warden import APP_NAME, __version__
from warden.config import ConfigError, load_all
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

    try:
        config = load_all()
    except ConfigError as exc:
        logging.getLogger(__name__).error("config invalid: %s", exc)
        QMessageBox.critical(None, f"{APP_NAME} - config problem",
                             f"{exc}\n\nFix the file above (or delete it to restore defaults) and restart.")
        return 2

    window = MainWindow(config)
    window.show()
    bus().emit("app.ready", f"{APP_NAME} ready", level="info", preset=config.preset_id)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
