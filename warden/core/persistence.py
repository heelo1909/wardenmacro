"""Durable state across restarts and crashes (HANDOFF section 9).

``state.json`` holds cumulative AFK time per contract and all-time counters,
written atomically (temp file + rename) on every flush. ``PersistenceManager``
tracks a snapshot of the running session's own counters/in-match time so
periodic flushes add only the *delta* since the last flush - calling
``flush()`` every 30s (or on every event) is safe and never double-counts.

``sessions/<timestamp>.json`` is a complete summary written once, at the end
of a session - the per-session table the (future) History page will read.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from warden.core.state_machine import Counters

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


@dataclass
class ContractProgress:
    label: str
    target_hours: float
    cumulative_seconds: float = 0.0

    @property
    def cumulative_hours(self) -> float:
        return self.cumulative_seconds / 3600.0

    @property
    def fraction(self) -> float:
        return min(self.cumulative_hours / self.target_hours, 1.0) if self.target_hours > 0 else 0.0


@dataclass
class AllTimeCounters:
    respawns: int = 0
    reconnects: int = 0
    re_queues: int = 0
    loadout_fixes: int = 0
    time_lost_s: float = 0.0
    total_sessions: int = 0


@dataclass
class PersistedState:
    schema_version: int = SCHEMA_VERSION
    contracts: dict[str, ContractProgress] = field(default_factory=dict)
    all_time: AllTimeCounters = field(default_factory=AllTimeCounters)
    last_session_incomplete: bool = False
    last_session_preset_id: str | None = None
    last_session_started_at: float | None = None


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_state(path: Path) -> PersistedState:
    """Missing or corrupt state is never fatal - a fresh ``PersistedState`` is returned."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        if not isinstance(exc, FileNotFoundError):
            log.warning("state.json unreadable (%s); starting fresh", exc)
        return PersistedState()
    try:
        contracts = {k: ContractProgress(**v) for k, v in raw.get("contracts", {}).items()}
        all_time = AllTimeCounters(**raw.get("all_time", {}))
        return PersistedState(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            contracts=contracts,
            all_time=all_time,
            last_session_incomplete=raw.get("last_session_incomplete", False),
            last_session_preset_id=raw.get("last_session_preset_id"),
            last_session_started_at=raw.get("last_session_started_at"),
        )
    except TypeError as exc:
        log.warning("state.json has an unexpected shape (%s); starting fresh", exc)
        return PersistedState()


def save_state(path: Path, state: PersistedState) -> None:
    data = {
        "schema_version": state.schema_version,
        "contracts": {k: asdict(v) for k, v in state.contracts.items()},
        "all_time": asdict(state.all_time),
        "last_session_incomplete": state.last_session_incomplete,
        "last_session_preset_id": state.last_session_preset_id,
        "last_session_started_at": state.last_session_started_at,
    }
    _save_json(path, data)


@dataclass
class SessionSummary:
    preset_id: str
    label: str
    started_at: float
    ended_at: float
    duration_s: float
    in_match_s: float
    counters: dict
    incidents: list[str]


def save_session_summary(sessions_dir: Path, summary: SessionSummary) -> Path:
    path = Path(sessions_dir) / f"{time.strftime('%Y%m%d_%H%M%S', time.localtime(summary.ended_at))}.json"
    _save_json(path, asdict(summary))
    return path


def load_session_summaries(sessions_dir: Path) -> list[dict]:
    out = []
    for p in sorted(Path(sessions_dir).glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


class PersistenceManager:
    def __init__(self, state_path: Path, sessions_dir: Path, save_interval_s: float = 30.0,
                 clock=time.monotonic, wall_clock=time.time):
        self.state_path = Path(state_path)
        self.sessions_dir = Path(sessions_dir)
        self.save_interval_s = save_interval_s
        self.clock = clock
        self.wall_clock = wall_clock
        self.state = load_state(self.state_path)
        self._last_flush_monotonic = 0.0
        self._session_preset_id: str | None = None
        self._session_label = ""
        self._session_target_hours = 0.0
        self._session_started_wall = 0.0
        self._last_in_match_s = 0.0
        self._last_counters = _counters_dict(Counters())

    # -- session lifecycle -------------------------------------------------------

    def start_session(self, preset_id: str, label: str, target_hours: float) -> None:
        self._session_preset_id = preset_id
        self._session_label = label
        self._session_target_hours = target_hours
        self._session_started_wall = self.wall_clock()
        self._last_in_match_s = 0.0
        self._last_counters = _counters_dict(Counters())
        self.state.last_session_incomplete = True
        self.state.last_session_preset_id = preset_id
        self.state.last_session_started_at = self._session_started_wall
        self.state.all_time.total_sessions += 1
        save_state(self.state_path, self.state)
        self._last_flush_monotonic = self.clock()

    def verify_contract_hours(self, preset_id: str, label: str, target_hours: float, verified_hours: float) -> None:
        """Correct the banked total from an OCR read of the game's own counter
        (section 8.1). Resets this manager's own delta baseline to match - the
        caller must also reset its own elapsed-seconds tracker to 0, or the
        next flush would re-add the pre-verification session time on top.
        """
        entry = self.state.contracts.get(preset_id)
        if entry is None:
            entry = ContractProgress(label=label, target_hours=target_hours)
            self.state.contracts[preset_id] = entry
        entry.label = label
        entry.target_hours = target_hours
        entry.cumulative_seconds = max(verified_hours, 0.0) * 3600.0
        self._last_in_match_s = 0.0
        save_state(self.state_path, self.state)

    def maybe_flush(self, in_match_s: float, counters: Counters, force: bool = False) -> bool:
        now = self.clock()
        if not force and now - self._last_flush_monotonic < self.save_interval_s:
            return False
        self._apply_delta(in_match_s, counters)
        save_state(self.state_path, self.state)
        self._last_flush_monotonic = now
        return True

    def end_session(self, in_match_s: float, counters: Counters, incidents: list[str]) -> Path:
        self._apply_delta(in_match_s, counters)
        self.state.last_session_incomplete = False
        save_state(self.state_path, self.state)
        summary = SessionSummary(
            preset_id=self._session_preset_id or "",
            label=self._session_label,
            started_at=self._session_started_wall,
            ended_at=self.wall_clock(),
            duration_s=self.wall_clock() - self._session_started_wall,
            in_match_s=in_match_s,
            counters=_counters_dict(counters),
            incidents=list(incidents),
        )
        return save_session_summary(self.sessions_dir, summary)

    # -- internals -------------------------------------------------------

    def _apply_delta(self, in_match_s: float, counters: Counters) -> None:
        if self._session_preset_id is None:
            return
        d_in_match = max(in_match_s - self._last_in_match_s, 0.0)
        entry = self.state.contracts.get(self._session_preset_id)
        if entry is None:
            entry = ContractProgress(label=self._session_label, target_hours=self._session_target_hours)
            self.state.contracts[self._session_preset_id] = entry
        entry.label = self._session_label
        entry.target_hours = self._session_target_hours
        entry.cumulative_seconds += d_in_match

        now_counters = _counters_dict(counters)
        at = self.state.all_time
        at.respawns += max(now_counters["respawns"] - self._last_counters["respawns"], 0)
        at.reconnects += max(now_counters["reconnects"] - self._last_counters["reconnects"], 0)
        at.re_queues += max(now_counters["re_queues"] - self._last_counters["re_queues"], 0)
        at.loadout_fixes += max(now_counters["loadout_fixes"] - self._last_counters["loadout_fixes"], 0)
        at.time_lost_s += max(now_counters["time_lost_s"] - self._last_counters["time_lost_s"], 0.0)

        self._last_in_match_s = in_match_s
        self._last_counters = now_counters


def _counters_dict(c: Counters) -> dict:
    return {"respawns": c.respawns, "reconnects": c.reconnects, "re_queues": c.re_queues,
            "loadout_fixes": c.loadout_fixes, "time_lost_s": c.time_lost_s}
