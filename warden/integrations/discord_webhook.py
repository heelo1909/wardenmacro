"""Discord webhook (HANDOFF section 8.2): a status embed every N minutes,
plus instant alerts (disconnect, recovery result, unknown screen, a
milestone every ``milestone_hours``, target reached).

``poster`` is injectable so nothing in here ever makes a real HTTP call
during tests - the default implementation is the only thing that touches
``requests``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

COLOR_INFO = 0xF2A93B
COLOR_SUCCESS = 0x3FB97A
COLOR_ERROR = 0xE5534B


def _default_poster(url: str, payload: dict) -> None:
    import requests

    requests.post(url, json=payload, timeout=10).raise_for_status()


class DiscordWebhook:
    def __init__(
        self,
        url: str,
        enabled: bool = True,
        interval_min: float = 15.0,
        milestone_hours: float = 4.0,
        clock: Callable[[], float] = time.monotonic,
        poster: Callable[[str, dict], None] = _default_poster,
    ):
        self.url = url
        self.enabled = enabled
        self.interval_s = max(interval_min, 1.0) * 60.0
        self.milestone_hours = milestone_hours
        self.clock = clock
        self.poster = poster
        self._last_status_at = float("-inf")
        self._last_milestone_index = 0
        self._target_alerted = False

    def _ready(self) -> bool:
        return self.enabled and bool(self.url.strip())

    def _send(self, title: str, description: str, color: int = COLOR_INFO, fields: list | None = None) -> bool:
        if not self._ready():
            return False
        embed = {"title": title, "description": description, "color": color}
        if fields:
            embed["fields"] = fields
        try:
            self.poster(self.url, {"embeds": [embed]})
            return True
        except Exception:
            log.exception("discord webhook post failed")
            return False

    # -- periodic status -------------------------------------------------------

    def maybe_send_status(self, state: str, counters: dict, hours_credited: float, target_hours: float) -> bool:
        if not self._ready():
            return False
        now = self.clock()
        if now - self._last_status_at < self.interval_s:
            return False
        remaining = max(target_hours - hours_credited, 0.0)
        fields = [
            {"name": "State", "value": state, "inline": True},
            {"name": "Progress", "value": f"{hours_credited:.2f}h / {target_hours:.1f}h", "inline": True},
            {"name": "Remaining", "value": f"{remaining:.2f}h", "inline": True},
            {"name": "Respawns", "value": str(counters.get("respawns", 0)), "inline": True},
            {"name": "Reconnects", "value": str(counters.get("reconnects", 0)), "inline": True},
            {"name": "Loadout fixes", "value": str(counters.get("loadout_fixes", 0)), "inline": True},
        ]
        sent = self._send("Warden status", f"Currently: {state}", fields=fields)
        if sent:
            self._last_status_at = now
        return sent

    # -- instant alerts -------------------------------------------------------

    def alert_disconnect(self, cause: str) -> bool:
        return self._send("Disconnected", f"Recovery triggered: {cause}", color=COLOR_ERROR)

    def alert_recovery_result(self, success: bool, attempts: int, method: str) -> bool:
        title = "Recovery succeeded" if success else "Recovery failed"
        return self._send(title, f"{attempts} attempt(s), method: {method}",
                          color=COLOR_SUCCESS if success else COLOR_ERROR)

    def alert_unknown_screen(self) -> bool:
        return self._send("Unknown screen", "Nothing recognized for too long - recovering.", color=COLOR_ERROR)

    def check_milestone(self, hours_credited: float) -> bool:
        if not self._ready() or self.milestone_hours <= 0:
            return False
        index = int(hours_credited // self.milestone_hours)
        if index <= self._last_milestone_index or index == 0:
            return False
        self._last_milestone_index = index
        return self._send("Milestone", f"{index * self.milestone_hours:.0f}h of playtime reached.",
                          color=COLOR_SUCCESS)

    def check_target_reached(self, hours_credited: float, target_hours: float) -> bool:
        if not self._ready() or self._target_alerted or hours_credited < target_hours:
            return False
        self._target_alerted = True
        return self._send("Target reached", f"Contract target of {target_hours:.1f}h reached!",
                          color=COLOR_SUCCESS)

    def reset_session_state(self) -> None:
        """Call at the start of a new session so milestones/target can alert again."""
        self._last_milestone_index = 0
        self._target_alerted = False
