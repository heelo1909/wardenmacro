"""Logging setup: one rotating log file per session plus an event-bus bridge."""

from __future__ import annotations

import logging
import logging.handlers
import time
from pathlib import Path

from warden import paths
from warden.core.events import Event, EventBus, Level

SUCCESS = int(Level.SUCCESS)
logging.addLevelName(SUCCESS, "SUCCESS")

_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.DEBUG, log_dir: Path | None = None, console: bool = True) -> Path:
    """Configure the root logger; returns the log file path for this run."""
    log_dir = log_dir or paths.data_dir("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"warden_{time.strftime('%Y%m%d_%H%M%S')}.log"

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_warden", False):
            root.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT, _DATEFMT)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler._warden = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if console:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        stream.setLevel(logging.INFO)
        stream._warden = True  # type: ignore[attr-defined]
        root.addHandler(stream)

    _prune_old_logs(log_dir, keep=30)
    return log_file


def _prune_old_logs(log_dir: Path, keep: int) -> None:
    files = sorted(log_dir.glob("warden_*.log*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def bridge_bus_to_logging(event_bus: EventBus) -> int:
    """Mirror every bus event into the log file."""
    logger = logging.getLogger("warden.events")

    def _write(event: Event) -> None:
        conf = f" (conf {event.confidence:.2f})" if event.confidence is not None else ""
        logger.log(int(event.level), "[%s] %s%s", event.topic, event.message, conf)

    return event_bus.subscribe(_write)
