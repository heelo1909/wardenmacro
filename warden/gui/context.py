"""Shared, mutable state every GUI page reads/writes - the config, the event
bus, and the (lazily built) TickLoop. One instance, owned by MainWindow,
passed to every page.
"""

from __future__ import annotations

import logging
from pathlib import Path

from warden.config import loader
from warden.config.loader import LoadedConfig
from warden.config.schema import AppConfig, Preset
from warden.core.events import EventBus
from warden.core.tick import TickLoop

log = logging.getLogger(__name__)


class AppContext:
    def __init__(self, loaded: LoadedConfig, bus: EventBus):
        self.app: AppConfig = loaded.app
        self.preset: Preset = loaded.preset
        self.preset_id: str = loaded.preset_id
        self.app_path: Path = loaded.app_path
        self.preset_path: Path = loaded.preset_path
        self.bus = bus
        self.tick_loop: TickLoop | None = None

    @property
    def presets_dir(self) -> Path:
        return self.preset_path.parent

    def available_presets(self) -> dict[str, Path]:
        return loader.list_presets(self.presets_dir)

    def set_active_preset(self, preset_id: str) -> None:
        presets = self.available_presets()
        if preset_id not in presets:
            raise KeyError(preset_id)
        self.preset = loader.load_preset(presets[preset_id])
        self.preset_id = preset_id
        self.preset_path = presets[preset_id]
        self.app.active_preset = preset_id
        self.save_app_config()

    def save_app_config(self) -> None:
        loader.save_model(self.app, self.app_path)

    def save_preset(self) -> None:
        loader.save_model(self.preset, self.preset_path)

    def create_preset(self, preset_id: str, source: Preset) -> Path:
        path = self.presets_dir / f"{preset_id}.yaml"
        if path.exists():
            raise FileExistsError(preset_id)
        loader.save_model(source, path)
        return path

    def delete_preset(self, preset_id: str) -> None:
        if preset_id == self.preset_id:
            raise ValueError("cannot delete the active preset")
        path = self.available_presets().get(preset_id)
        if path:
            path.unlink()

    def ensure_tick_loop(self) -> TickLoop:
        """(Re)build the TickLoop from the current config - cheap, and
        guarantees Start always uses whatever was just changed in Settings.
        """
        if self.tick_loop is not None:
            self.tick_loop.stop()
        self.tick_loop = TickLoop(self.app, self.preset, self.bus)
        return self.tick_loop

    def persisted_state(self):
        """Durable state from a prior session (section 9), read fresh each
        call - cheap, and always current even if nothing has started yet.
        """
        from warden import paths
        from warden.core.persistence import load_state

        return load_state(paths.data_home() / "state.json")

    def session_summaries(self) -> list[dict]:
        """Every past session Warden has finished (section 9's ``sessions/*.json``),
        oldest first. Used by Home's chart and the History page's past-sessions
        table; cheap enough (a handful of small JSON files) to call on every
        refresh without caching.
        """
        from warden import paths
        from warden.core.persistence import load_session_summaries

        return load_session_summaries(paths.data_dir("sessions"))

    def contract_banked_hours(self, preset_id: str | None = None) -> float:
        """Cumulative hours already credited to a contract from past sessions."""
        entry = self.persisted_state().contracts.get(preset_id or self.preset_id)
        return entry.cumulative_hours if entry else 0.0

    def next_in_contract_queue(self) -> str | None:
        """The preset after the active one in ``contract_queue``, if any (HANDOFF §8.11)."""
        queue = self.app.contract_queue
        if self.preset_id not in queue:
            return None
        i = queue.index(self.preset_id)
        return queue[i + 1] if i + 1 < len(queue) else None

    def advance_contract_queue(self) -> bool:
        """Switch to the next preset in the queue. Returns False if there isn't one."""
        nxt = self.next_in_contract_queue()
        if nxt is None:
            return False
        self.set_active_preset(nxt)
        return True
